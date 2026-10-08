"""Synthetic registration, email verification, and approval lifecycle tests."""

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.config import settings
from app.db import AsyncSessionLocal, engine
from app.main import app
from app.models import Organization, RegistrationStatus, User, UserRole
from app.models.organization import DEFAULT_ORGANIZATION_ID
from app.routers import auth as auth_router
from app.routers import admin_auth as admin_auth_router
from app.security.auth import create_access_token, hash_password
from app.services import verification_codes
from app.services.email_templates import EmailTemplate


@pytest_asyncio.fixture(autouse=True)
async def dispose_db_engine_per_test_loop():
    await engine.dispose(close=False)
    yield
    await engine.dispose(close=False)


def transport() -> ASGITransport:
    return ASGITransport(app=app, client=(f"198.51.100.{uuid.uuid4().int % 200 + 1}", 43210))


async def csrf(client: AsyncClient) -> dict[str, str]:
    await client.get("/api/v1/auth/csrf")
    return {"X-CSRF-Token": client.cookies.get("mdis_csrf")}


def registration_payload(email: str, **extra) -> dict[str, object]:
    return {
        "full_name": "Synthetic Test Clinician",
        "work_email": email,
        "organization_request_name": "Synthetic Clinic Request",
        "professional_role": "doctor",
        "license_or_certification_number": "SYN-12345",
        "license_type": "medical",
        "password": "Stellar paper orbit phrase 481!",
        "confirm_password": "Stellar paper orbit phrase 481!",
        "phone": "+1 555 0100",
        "accepted_terms": True,
        **extra,
    }


async def make_admin(org_id=DEFAULT_ORGANIZATION_ID, *, create_org=False) -> User:
    admin = User(
        email=f"stage3-admin-{uuid.uuid4()}@example.test",
        display_name="Synthetic Clinic Admin",
        password_hash=hash_password("Synthetic admin password 873!"),
        role=UserRole.ADMIN,
        organization_id=org_id,
        is_active=True,
        mfa_enabled=True,
    )
    async with AsyncSessionLocal() as db:
        if create_org:
            db.add(Organization(id=org_id, name=f"Synthetic Org {org_id}"))
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
    return admin


@pytest.mark.asyncio
async def test_registration_verification_and_status_only_login(monkeypatch):
    monkeypatch.setattr(settings, "registration_mode", "approval")
    monkeypatch.setattr(settings, "auth_enumeration_min_response_ms", 0)
    monkeypatch.setattr(auth_router, "email_delivery_available", lambda: True)
    monkeypatch.setattr(verification_codes, "email_delivery_available", lambda: True)
    sent: list[tuple[str, str, str]] = []

    async def capture_code(email: str, purpose: str, code: str) -> None:
        sent.append((email, purpose, code))

    monkeypatch.setattr(verification_codes, "_deliver_verification_code", capture_code)
    email = f"registration-{uuid.uuid4()}@example.test"
    payload = registration_payload(email)
    payload.pop("organization_request_name")
    payload["organization_id"] = str(DEFAULT_ORGANIZATION_ID)
    async with AsyncClient(transport=transport(), base_url="http://test") as client:
        headers = await csrf(client)
        registered = await client.post("/api/v1/auth/register", json=payload, headers=headers)
        assert registered.status_code == 202
        assert len(sent) == 1 and sent[0][1] == "verify_email"
        pending_login = await client.post("/api/v1/auth/login", json={"email": email, "password": "Stellar paper orbit phrase 481!"}, headers=headers)
        assert pending_login.status_code == 200
        assert pending_login.json()["status"] == "pending_email_verification"
        assert "mdis_access" not in pending_login.cookies
        assert (await client.get("/api/v1/patients")).status_code == 401

        verified = await client.post("/api/v1/auth/verify-email", json={"email": email, "code": sent[0][2]}, headers=headers)
        assert verified.status_code == 200
        assert verified.json()["status"] == "pending_approval"
        approval_login = await client.post("/api/v1/auth/login", json={"email": email, "password": "Stellar paper orbit phrase 481!"}, headers=headers)
        assert approval_login.status_code == 200
        assert approval_login.json()["status"] == "pending_approval"
        assert "mdis_access" not in approval_login.cookies
        assert (await client.get("/api/v1/patients")).status_code == 401

    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User).where(User.email == email))
        assert user is not None
        assert user.registration_status == RegistrationStatus.PENDING_APPROVAL.value
        assert user.email_verified is True
        assert user.role == UserRole.VIEWER
        assert user.professional_role_requested == "doctor"
        assert user.license_or_certification_number == "SYN-12345"
        assert not user.is_active


@pytest.mark.asyncio
async def test_registration_rejects_role_escalation_and_invalid_terms(monkeypatch):
    monkeypatch.setattr(settings, "registration_mode", "approval")
    monkeypatch.setattr(settings, "auth_enumeration_min_response_ms", 0)
    monkeypatch.setattr(auth_router, "email_delivery_available", lambda: True)
    email = f"escalation-{uuid.uuid4()}@example.test"
    async with AsyncClient(transport=transport(), base_url="http://test") as client:
        headers = await csrf(client)
        escalation = await client.post(
            "/api/v1/auth/register",
            json=registration_payload(email, role="admin", system_role="operator"),
            headers=headers,
        )
        assert escalation.status_code == 422
        no_terms = await client.post(
            "/api/v1/auth/register",
            json=registration_payload(f"terms-{uuid.uuid4()}@example.test", accepted_terms=False),
            headers=headers,
        )
        assert no_terms.status_code == 422
    async with AsyncSessionLocal() as db:
        assert await db.scalar(select(User.id).where(User.email == email)) is None


@pytest.mark.asyncio
async def test_admin_approval_and_rejection_are_organization_scoped(monkeypatch):
    monkeypatch.setattr(settings, "registration_mode", "approval")
    monkeypatch.setattr(settings, "auth_enumeration_min_response_ms", 0)
    monkeypatch.setattr(auth_router, "email_delivery_available", lambda: True)
    monkeypatch.setattr(verification_codes, "email_delivery_available", lambda: True)
    sent: list[tuple[str, str, str]] = []
    notices: list[tuple[str, EmailTemplate]] = []

    async def capture_code(email: str, purpose: str, code: str) -> None:
        sent.append((email, purpose, code))

    monkeypatch.setattr(verification_codes, "_deliver_verification_code", capture_code)

    async def capture_notice(email: str, template: EmailTemplate, _name: str = "") -> bool:
        notices.append((email, template))
        return True

    monkeypatch.setattr(admin_auth_router, "configured_email_provider", lambda: object())
    monkeypatch.setattr(admin_auth_router, "send_account_notice", capture_notice)
    email = f"review-{uuid.uuid4()}@example.test"
    payload = registration_payload(email)
    payload.pop("organization_request_name")
    payload["organization_id"] = str(DEFAULT_ORGANIZATION_ID)
    admin = await make_admin()
    token = create_access_token({"sub": str(admin.id)})
    async with AsyncClient(transport=transport(), base_url="http://test") as client:
        headers = await csrf(client)
        headers["Authorization"] = f"Bearer {token}"
        me = await client.get("/api/v1/auth/me", headers=headers)
        assert me.status_code == 200, me.text
        registered = await client.post("/api/v1/auth/register", json=payload, headers=headers)
        assert registered.status_code == 202
        verified = await client.post("/api/v1/auth/verify-email", json={"email": email, "code": sent[-1][2]}, headers=headers)
        assert verified.status_code == 200
        async with AsyncSessionLocal() as db:
            candidate = await db.scalar(select(User).where(User.email == email))
            assert candidate is not None
            candidate_id = candidate.id

        other_admin = await make_admin(uuid.uuid4(), create_org=True)
        other_token = create_access_token({"sub": str(other_admin.id)})
        async with AsyncClient(transport=transport(), base_url="http://test", headers={"Authorization": f"Bearer {other_token}"}) as other_client:
            other_queue = await other_client.get("/api/v1/admin/account-requests")
            assert other_queue.status_code == 200
            assert all(row["id"] != str(candidate_id) for row in other_queue.json()["items"])

        me_after = await client.get("/api/v1/auth/me", headers=headers)
        assert me_after.status_code == 200, me_after.text
        queue = await client.get("/api/v1/admin/account-requests", headers=headers)
        assert queue.status_code == 200, queue.text
        assert any(row["id"] == str(candidate_id) for row in queue.json()["items"])
        approved = await client.post(f"/api/v1/admin/account-requests/{candidate_id}/approve", json={"role": "clinician"}, headers=headers)
        assert approved.status_code == 200
        assert approved.json()["email_delivery"] == "queued"
        assert (email, EmailTemplate.ACCOUNT_APPROVED) in notices
        login = await client.post("/api/v1/auth/login", json={"email": email, "password": "Stellar paper orbit phrase 481!"}, headers=headers)
        assert login.status_code == 200 and login.json()["user"]["role"] == "clinician"

        cross_org = await client.post(
            f"/api/v1/admin/account-requests/{candidate_id}/reject",
            json={"reason": "Synthetic reason"},
            headers={**headers, "Authorization": f"Bearer {other_token}"},
        )
        assert cross_org.status_code == 404

        unmatched_email = f"unmatched-org-{uuid.uuid4()}@example.test"
        await client.post("/api/v1/auth/register", json=registration_payload(unmatched_email), headers=headers)
        await client.post("/api/v1/auth/verify-email", json={"email": unmatched_email, "code": sent[-1][2]}, headers=headers)
        async with AsyncSessionLocal() as db:
            unmatched = await db.scalar(select(User).where(User.email == unmatched_email))
            assert unmatched is not None
            unmatched_id = unmatched.id
        cannot_approve_unmapped_org = await client.post(
            f"/api/v1/admin/account-requests/{unmatched_id}/approve",
            json={"role": "clinician"},
            headers=headers,
        )
        assert cannot_approve_unmapped_org.status_code == 409

    rejected_email = f"reject-{uuid.uuid4()}@example.test"
    rejected_admin = create_access_token({"sub": str(admin.id)})
    async with AsyncClient(transport=transport(), base_url="http://test") as client:
        headers = await csrf(client)
        headers["Authorization"] = f"Bearer {rejected_admin}"
        await client.post("/api/v1/auth/register", json=registration_payload(rejected_email), headers=headers)
        await client.post("/api/v1/auth/verify-email", json={"email": rejected_email, "code": sent[-1][2]}, headers=headers)
        async with AsyncSessionLocal() as db:
            candidate = await db.scalar(select(User).where(User.email == rejected_email))
            assert candidate is not None
            candidate_id = candidate.id
        rejected = await client.post(
            f"/api/v1/admin/account-requests/{candidate_id}/reject",
            json={"reason": "Synthetic review reason"},
            headers=headers,
        )
        assert rejected.status_code == 200
        assert rejected.json()["email_delivery"] == "queued"
        assert (rejected_email, EmailTemplate.ACCOUNT_REJECTED) in notices
        status_login = await client.post("/api/v1/auth/login", json={"email": rejected_email, "password": "Stellar paper orbit phrase 481!"}, headers=headers)
        assert status_login.status_code == 200
        assert status_login.json()["status"] == "rejected"
        assert status_login.json()["rejection_reason"] == "Synthetic review reason"
        assert "mdis_access" not in status_login.cookies


@pytest.mark.asyncio
async def test_registration_modes_and_duplicate_email_notice(monkeypatch):
    from app.services import email_provider

    monkeypatch.setattr(settings, "auth_enumeration_min_response_ms", 0)
    monkeypatch.setattr(auth_router, "email_delivery_available", lambda: True)
    monkeypatch.setattr(verification_codes, "email_delivery_available", lambda: True)
    notices: list[tuple[str, EmailTemplate]] = []

    async def capture_notice(email: str, template: EmailTemplate, _name: str = "") -> bool:
        notices.append((email, template))
        return True

    monkeypatch.setattr(email_provider, "send_account_notice", capture_notice)
    monkeypatch.setattr(auth_router, "send_account_notice", capture_notice)
    existing_email = f"duplicate-{uuid.uuid4()}@example.test"
    existing = User(
        email=existing_email,
        display_name="Synthetic Existing Account",
        password_hash=hash_password("Synthetic existing password 492!"),
        role=UserRole.CLINICIAN,
        organization_id=DEFAULT_ORGANIZATION_ID,
        is_active=True,
    )
    async with AsyncSessionLocal() as db:
        db.add(existing)
        await db.commit()

    async with AsyncClient(transport=transport(), base_url="http://test") as client:
        headers = await csrf(client)
        monkeypatch.setattr(settings, "registration_mode", "invite_only")
        locked = await client.post("/api/v1/auth/register", json=registration_payload(f"closed-{uuid.uuid4()}@example.test"), headers=headers)
        assert locked.status_code == 404
        monkeypatch.setattr(settings, "registration_mode", "approval")
        duplicate = await client.post("/api/v1/auth/register", json=registration_payload(existing_email), headers=headers)
        assert duplicate.status_code == 202
        assert "already exists" not in duplicate.text.lower()
        assert notices == [(existing_email, EmailTemplate.ACCOUNT_EXISTS)]
