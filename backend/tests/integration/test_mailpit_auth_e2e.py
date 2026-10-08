"""Opt-in real SMTP/Mailpit test for the registration, approval, and reset journey.

Run against a disposable PostgreSQL database with the backend configured for
SMTP-to-Mailpit. The test does not replace email delivery or provider calls.
"""

import asyncio
import os
import re
import uuid

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.config import settings
from app.db import AsyncSessionLocal, engine
from app.main import app
from app.models import User, UserRole
from app.models.organization import DEFAULT_ORGANIZATION_ID
from app.security.auth import create_access_token, hash_password


pytestmark = pytest.mark.skipif(
    os.getenv("MDIS_MAILPIT_E2E") != "1",
    reason="set MDIS_MAILPIT_E2E=1 to run against configured SMTP and Mailpit",
)


@pytest_asyncio.fixture(autouse=True)
async def dispose_db_engine_per_test_loop():
    await engine.dispose(close=False)
    yield
    await engine.dispose(close=False)


async def csrf(client: AsyncClient) -> dict[str, str]:
    response = await client.get("/api/v1/auth/csrf")
    assert response.status_code == 200
    return {"X-CSRF-Token": client.cookies.get("mdis_csrf", "")}


async def wait_for_code(mailpit: httpx.AsyncClient, recipient: str) -> str:
    """Poll Mailpit without writing the message or code to test output."""
    deadline = asyncio.get_running_loop().time() + 20
    while asyncio.get_running_loop().time() < deadline:
        response = await mailpit.get(
            "/api/v1/messages", params={"query": f"to:{recipient}", "limit": 20}
        )
        assert response.status_code == 200
        for message in response.json().get("messages", []):
            detail = await mailpit.get(f"/api/v1/message/{message['ID']}")
            assert detail.status_code == 200
            match = re.search(
                r"Your one-time code:\s*(\d{6})", detail.json().get("Text", "")
            )
            if match:
                return match.group(1)
        await asyncio.sleep(0.25)
    pytest.fail("No verification message arrived in Mailpit before timeout")


@pytest.mark.asyncio
async def test_registration_approval_and_password_reset_with_real_mailpit(monkeypatch):
    """Exercise real API handlers and SMTP delivery using synthetic identities."""
    from app.models import Organization

    mailpit_url = os.getenv("MAILPIT_URL", "http://127.0.0.1:8025")
    database_name = make_url(settings.database_url).database or ""
    if "test" not in database_name.lower() and "e2e" not in database_name.lower():
        pytest.fail("Refusing to run Mailpit E2E unless DATABASE_URL names a test/e2e database")
    if settings.email_provider != "smtp" or not settings.smtp_host:
        pytest.fail("Configure EMAIL_PROVIDER=smtp and SMTP_HOST=mailpit for this test")
    monkeypatch.setattr(settings, "registration_mode", "approval")
    monkeypatch.setattr(settings, "auth_enumeration_min_response_ms", 0)

    admin_email = f"mailpit-admin-{uuid.uuid4()}@example.test"
    admin = User(
        email=admin_email,
        display_name="Synthetic Mailpit Administrator",
        password_hash=hash_password("Synthetic admin passphrase 421!"),
        role=UserRole.ADMIN,
        organization_id=DEFAULT_ORGANIZATION_ID,
        is_active=True,
        mfa_enabled=True,
    )
    async with AsyncSessionLocal() as db:
        if await db.get(Organization, DEFAULT_ORGANIZATION_ID) is None:
            pytest.fail("The test database must be migrated and seeded with its default organization")
        db.add(admin)
        await db.commit()
        await db.refresh(admin)

    email = f"mailpit-user-{uuid.uuid4()}@example.test"
    original_password = "Registration orbit stellar 735!"
    replacement_password = "Replacement copper harbor 296!"
    transport = ASGITransport(
        app=app,
        client=(f"198.51.100.{uuid.uuid4().int % 200 + 1}", 43210),
    )
    async with httpx.AsyncClient(base_url=mailpit_url, timeout=5) as mailpit:
        async with AsyncClient(transport=transport, base_url="http://test") as applicant:
            request_headers = await csrf(applicant)
            registration = await applicant.post(
                "/api/v1/auth/register",
                headers=request_headers,
                json={
                    "full_name": "Synthetic Mailpit Applicant",
                    "work_email": email,
                    "organization_id": str(DEFAULT_ORGANIZATION_ID),
                    "professional_role": "doctor",
                    "license_or_certification_number": "SYN-E2E-001",
                    "license_type": "medical",
                    "password": original_password,
                    "confirm_password": original_password,
                    "accepted_terms": True,
                },
            )
            if registration.status_code != 202:
                details = registration.json().get("detail", [])
                safe_errors = [
                    {"loc": item.get("loc"), "msg": item.get("msg")}
                    for item in details
                    if isinstance(item, dict)
                ]
                pytest.fail(f"Synthetic registration was rejected: {safe_errors}")
            verification_code = await wait_for_code(mailpit, email)
            verified = await applicant.post(
                "/api/v1/auth/verify-email",
                headers=request_headers,
                json={"email": email, "code": verification_code},
            )
            assert verified.status_code == 200
            assert verified.json()["status"] == "pending_approval"

        admin_token = create_access_token({"sub": str(admin.id)})
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Authorization": f"Bearer {admin_token}"},
        ) as administrator:
            admin_headers = await csrf(administrator)
            queue = await administrator.get("/api/v1/admin/account-requests")
            assert queue.status_code == 200
            candidate = next(item for item in queue.json()["items"] if item["email"] == email)
            approved = await administrator.post(
                f"/api/v1/admin/account-requests/{candidate['id']}/approve",
                headers=admin_headers,
                json={"role": "clinician"},
            )
            assert approved.status_code == 200
            assert approved.json()["email_delivery"] == "queued"

        # The approval notice is link-free but must be delivered to the test inbox.
        inbox = await mailpit.get(
            "/api/v1/messages", params={"query": f"to:{email}", "limit": 20}
        )
        assert inbox.status_code == 200
        assert any("approved" in row.get("Subject", "").lower() for row in inbox.json().get("messages", []))

        async with AsyncClient(transport=transport, base_url="http://test") as old_session:
            old_headers = await csrf(old_session)
            signed_in = await old_session.post(
                "/api/v1/auth/login",
                headers=old_headers,
                json={"email": email, "password": original_password},
            )
            assert signed_in.status_code == 200
            assert (await old_session.get("/api/v1/auth/me")).status_code == 200
            requested = await old_session.post(
                "/api/v1/auth/forgot-password", headers=old_headers, json={"email": email}
            )
            assert requested.status_code == 200
            assert requested.json()["message"] == "If the account exists, an email has been sent"
            reset_code = await wait_for_code(mailpit, email)
            verified_code = await old_session.post(
                "/api/v1/auth/verify-reset-code",
                headers=old_headers,
                json={"email": email, "code": reset_code},
            )
            assert verified_code.status_code == 200
            reset = await old_session.post(
                "/api/v1/auth/reset-password",
                headers=old_headers,
                json={
                    "grant": verified_code.json()["grant"],
                    "new_password": replacement_password,
                    "confirm_password": replacement_password,
                },
            )
            assert reset.status_code == 200
            assert (await old_session.get("/api/v1/auth/me")).status_code == 401

        async with AsyncClient(transport=transport, base_url="http://test") as new_session:
            new_headers = await csrf(new_session)
            relogin = await new_session.post(
                "/api/v1/auth/login",
                headers=new_headers,
                json={"email": email, "password": replacement_password},
            )
            assert relogin.status_code == 200
            assert relogin.json()["user"]["email"] == email

    async with AsyncSessionLocal() as db:
        created = await db.scalar(select(User).where(User.email == email))
        assert created is not None and created.is_active
