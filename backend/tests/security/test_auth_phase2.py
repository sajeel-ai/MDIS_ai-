"""Synthetic regression coverage for account recovery, MFA and abuse controls."""

import uuid
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.config import settings
from app.db import AsyncSessionLocal, engine
from app.main import app
from app.models import AuditEvent, AuthActionToken, RefreshToken, User, UserRole
from app.models.organization import DEFAULT_ORGANIZATION_ID
from app.routers import auth as auth_router
from app.routers import admin_auth
from app.security.auth import create_access_token, hash_password
from app.security.mfa import decrypt_secret, encrypt_secret, new_totp_secret, recovery_hash, totp, verify_totp
from app.services.auth_rate_limit import enforce_auth_rate_limit
from app.services import verification_codes


@pytest_asyncio.fixture(autouse=True)
async def isolate_asyncpg_connections_per_test_loop():
    await engine.dispose(close=False)
    yield
    await engine.dispose(close=False)


async def make_user(role: UserRole = UserRole.CLINICIAN, *, active: bool = True, mfa_enabled: bool = False) -> User:
    user = User(
        email=f"phase2-{uuid.uuid4()}@example.test",
        display_name="Synthetic Phase Two User",
        password_hash=hash_password("synthetic secure phrase 89!"),
        role=role,
        organization_id=DEFAULT_ORGANIZATION_ID,
        is_active=active,
        email_verified=active,
        registration_status="approved" if active else "pending_email_verification",
        mfa_enabled=mfa_enabled,
    )
    async with AsyncSessionLocal() as db:
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


async def csrf(client: AsyncClient) -> dict[str, str]:
    await client.get("/api/v1/auth/csrf")
    return {"X-CSRF-Token": client.cookies.get("mdis_csrf")}


def request_from_ip(ip: str, headers=None):
    return SimpleNamespace(client=SimpleNamespace(host=ip), headers=headers or {})


def phase2_transport() -> ASGITransport:
    return ASGITransport(app=app, client=(f"192.0.2.{uuid.uuid4().int % 250 + 1}", 54321))


def test_totp_encryption_and_single_use_recovery_hashes():
    secret = new_totp_secret()
    encrypted = encrypt_secret(secret)
    assert encrypted != secret
    assert decrypt_secret(encrypted) == secret
    code = totp(secret)
    assert verify_totp(secret, code)
    assert not verify_totp(secret, "000000" if code != "000000" else "111111")
    assert recovery_hash("random recovery value") != "random recovery value"


@pytest.mark.asyncio
async def test_rate_limit_counts_by_ip_and_returns_retry_after(monkeypatch):
    monkeypatch.setattr(settings, "auth_rate_limit_per_ip", 2)
    ip = f"198.51.100.{uuid.uuid4().int % 200 + 1}"
    async with AsyncSessionLocal() as db:
        await enforce_auth_rate_limit(request_from_ip(ip), db, "phase2-test")
        await enforce_auth_rate_limit(request_from_ip(ip), db, "phase2-test")
        with pytest.raises(HTTPException) as raised:
            await enforce_auth_rate_limit(request_from_ip(ip), db, "phase2-test")
    assert raised.value.status_code == 429
    assert "Retry-After" in raised.value.headers


@pytest.mark.asyncio
async def test_rate_limit_counts_per_account_across_ips(monkeypatch):
    monkeypatch.setattr(settings, "auth_rate_limit_per_ip", 100)
    monkeypatch.setattr(settings, "auth_rate_limit_per_account", 2)
    account = f"account-{uuid.uuid4()}"
    async with AsyncSessionLocal() as db:
        await enforce_auth_rate_limit(request_from_ip("192.0.2.21"), db, "phase2-account-test", account)
        await enforce_auth_rate_limit(request_from_ip("192.0.2.22"), db, "phase2-account-test", account)
        with pytest.raises(HTTPException) as raised:
            await enforce_auth_rate_limit(request_from_ip("192.0.2.23"), db, "phase2-account-test", account)
    assert raised.value.status_code == 429


@pytest.mark.asyncio
async def test_rate_limit_cannot_be_bypassed_by_spoofing_forwarded_ip(monkeypatch):
    monkeypatch.setattr(settings, "auth_rate_limit_per_ip", 2)
    socket_ip = f"198.51.100.{uuid.uuid4().int % 200 + 1}"
    async with AsyncSessionLocal() as db:
        await enforce_auth_rate_limit(request_from_ip(socket_ip, {"x-forwarded-for": "203.0.113.1"}), db, "phase5-forwarded-ip")
        await enforce_auth_rate_limit(request_from_ip(socket_ip, {"x-forwarded-for": "203.0.113.2"}), db, "phase5-forwarded-ip")
        with pytest.raises(HTTPException) as raised:
            await enforce_auth_rate_limit(request_from_ip(socket_ip, {"x-forwarded-for": "203.0.113.3"}), db, "phase5-forwarded-ip")
    assert raised.value.status_code == 429


@pytest.mark.asyncio
async def test_forgot_password_code_grant_is_generic_single_use_and_revokes_sessions(monkeypatch):
    user = await make_user()
    session_family = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        stale_mfa_raw = "stale-mfa-challenge-" + secrets_token()
        db.add(RefreshToken(
            user_id=user.id,
            family_id=session_family,
            token_hash=auth_router._token_hash(f"synthetic-active-refresh-token-{uuid.uuid4()}"),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        ))
        db.add(AuthActionToken(
            purpose="mfa_login",
            user_id=user.id,
            token_hash=auth_router._token_hash(stale_mfa_raw),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        ))
        await db.commit()
    delivered: list[tuple[str, str, str]] = []

    async def capture(email: str, purpose: str, code: str):
        delivered.append((email, purpose, code))

    monkeypatch.setattr(verification_codes, "email_delivery_available", lambda: True)
    monkeypatch.setattr(verification_codes, "_deliver_verification_code", capture)
    old_access = create_access_token({"sub": str(user.id), "sid": str(session_family)})
    async with AsyncClient(transport=phase2_transport(), base_url="http://test") as client:
        headers = await csrf(client)
        audit_headers = {**headers, "User-Agent": "Test password=secret token=abc synthetic@example.test"}
        known = await client.post("/api/v1/auth/forgot-password", json={"email": user.email}, headers=audit_headers)
        unknown = await client.post("/api/v1/auth/forgot-password", json={"email": f"missing-{uuid.uuid4()}@example.test"}, headers=headers)
        assert known.status_code == unknown.status_code == 200
        assert known.json() == unknown.json() == {"message": "If the account exists, an email has been sent"}
        assert len(delivered) == 1 and delivered[0][0:2] == (user.email, "reset_password")
        code = delivered[0][2]
        assert code not in known.text and code not in unknown.text
        grant_response = await client.post("/api/v1/auth/verify-reset-code", json={"email": user.email, "code": code}, headers=headers)
        assert grant_response.status_code == 200
        grant = grant_response.json()["grant"]
        assert grant_response.json()["expires_in"] == 900
        async with AsyncSessionLocal() as db:
            grant_row = await db.scalar(select(AuthActionToken).where(AuthActionToken.token_hash == auth_router._token_hash(grant)))
            assert grant_row is not None and grant_row.token_hash != grant
        reset_payload = {"grant": grant, "new_password": "long reset password 827! secure", "confirm_password": "long reset password 827! secure"}
        reset = await client.post("/api/v1/auth/reset-password", json=reset_payload, headers=headers)
        assert reset.status_code == 200
        again = await client.post("/api/v1/auth/reset-password", json=reset_payload, headers=await csrf(client))
        assert again.status_code == 400
        stale_session = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old_access}"})
        assert stale_session.status_code == 401
    async with AsyncSessionLocal() as db:
        row = await db.scalar(select(AuthActionToken).where(AuthActionToken.token_hash == auth_router._token_hash(grant)))
        assert row is not None and row.used_at is not None
        event = await db.scalar(select(AuditEvent).where(AuditEvent.user_id == user.id, AuditEvent.action == "PASSWORD_RESET_COMPLETED").order_by(AuditEvent.created_at.desc()))
        revoked = await db.scalar(select(RefreshToken).where(RefreshToken.family_id == session_family))
        stale_mfa = await db.scalar(select(AuthActionToken).where(AuthActionToken.token_hash == auth_router._token_hash(stale_mfa_raw)))
        assert event and event.ip_address and event.request_id
        assert revoked is not None and revoked.revoked_at is not None
        assert stale_mfa is not None and stale_mfa.used_at is not None
        assert "secret" not in (event.user_agent or "").lower()
        assert "abc" not in (event.user_agent or "")
        assert "example.test" not in (event.user_agent or "")
        assert grant not in str(event.metadata_)
        assert user.email not in str(event.metadata_)


@pytest.mark.asyncio
async def test_forgot_password_fails_closed_when_email_delivery_is_unconfigured(monkeypatch):
    monkeypatch.setattr(verification_codes, "email_delivery_available", lambda: False)
    async with AsyncClient(transport=phase2_transport(), base_url="http://test") as client:
        headers = await csrf(client)
        response = await client.post("/api/v1/auth/forgot-password", json={"email": "synthetic@example.test"}, headers=headers)
    assert response.status_code == 503
    assert response.json() == {"detail": "Email delivery is not configured"}


@pytest.mark.asyncio
async def test_code_request_endpoint_is_generic_for_existing_and_unknown_emails(monkeypatch):
    user = await make_user(active=False)
    delivered: list[str] = []

    async def capture(_email: str, _purpose: str, code: str):
        delivered.append(code)
        return True

    monkeypatch.setattr(verification_codes, "email_delivery_available", lambda: True)
    monkeypatch.setattr(verification_codes, "send_verification_code", capture)
    async with AsyncClient(transport=phase2_transport(), base_url="http://test") as client:
        headers = await csrf(client)
        known = await client.post("/api/v1/auth/codes/request", json={"email": user.email, "purpose": "verify_email"}, headers=headers)
        unknown = await client.post("/api/v1/auth/codes/request", json={"email": f"missing-{uuid.uuid4()}@example.test", "purpose": "verify_email"}, headers=headers)
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json() == {"message": "If the account exists, we sent a code"}
    assert len(delivered) == 1 and delivered[0] not in known.text and delivered[0] not in unknown.text


@pytest.mark.asyncio
async def test_forgot_password_known_unknown_timing_is_bounded_by_response_floor(monkeypatch):
    user = await make_user()
    monkeypatch.setattr(verification_codes, "email_delivery_available", lambda: True)
    durations: dict[str, list[float]] = {"known": [], "unknown": []}
    async with AsyncClient(transport=phase2_transport(), base_url="http://test") as client:
        headers = await csrf(client)
        samples = [("unknown", f"missing-{uuid.uuid4()}@example.test"), ("known", user.email)] * 2
        for label, email in samples:
            started = time.perf_counter()
            response = await client.post("/api/v1/auth/forgot-password", json={"email": email}, headers=headers)
            durations[label].append(time.perf_counter() - started)
            assert response.status_code == 200
            assert response.json() == {"message": "If the account exists, an email has been sent"}

    known_median = sorted(durations["known"])[1]
    unknown_median = sorted(durations["unknown"])[1]
    # This is a noisy regression bound for the configured floor, not proof of constant-time behavior.
    assert abs(known_median - unknown_median) < settings.auth_enumeration_min_response_ms / 1000


@pytest.mark.asyncio
async def test_expired_password_reset_token_is_rejected():
    user = await make_user()
    raw = "expired-token-" + secrets_token()
    async with AsyncSessionLocal() as db:
        db.add(AuthActionToken(purpose="password_reset_grant", user_id=user.id, token_hash=auth_router._token_hash(raw), expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        await db.commit()
    async with AsyncClient(transport=phase2_transport(), base_url="http://test") as client:
        headers = await csrf(client)
        response = await client.post("/api/v1/auth/reset-password", json={"grant": raw, "new_password": "synthetic reset phrase 47!", "confirm_password": "synthetic reset phrase 47!"}, headers=headers)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_privileged_login_enrolls_then_returns_pending_mfa_before_session():
    user = await make_user(UserRole.ADMIN)
    async with AsyncClient(transport=phase2_transport(), base_url="http://test") as client:
        headers = await csrf(client)
        login = await client.post("/api/v1/auth/login", json={"email": user.email, "password": "synthetic secure phrase 89!"}, headers=headers)
        assert login.status_code == 403
        assert "mdis_mfa_setup" in client.cookies
        setup = await client.post("/api/v1/auth/mfa/setup", headers=headers)
        assert setup.status_code == 200
        secret = parse_qs(urlparse(setup.json()["provisioning_uri"]).query)["secret"][0]
        enabled = await client.post("/api/v1/auth/mfa/enable", json={"code": totp(secret)}, headers=headers)
        assert enabled.status_code == 200
        recovery_codes = enabled.json()["recovery_codes"]
        assert recovery_codes and "mdis_access" in client.cookies
        async with AsyncSessionLocal() as db:
            persisted = await db.get(User, user.id)
            assert persisted.mfa_enabled
            assert persisted.mfa_secret_encrypted != secret
            assert recovery_hash(recovery_codes[0]) in persisted.recovery_code_hashes

        logged_out = await client.post("/api/v1/auth/logout", headers=headers)
        assert logged_out.status_code == 204
        headers = await csrf(client)
        pending = await client.post("/api/v1/auth/login", json={"email": user.email, "password": "synthetic secure phrase 89!"}, headers=headers)
        assert pending.status_code == 200
        assert pending.json()["status"] == "pending_mfa"
        assert pending.json()["mfa_required"] is True
        assert "mdis_mfa_pending" in client.cookies
        assert "mdis_access" not in pending.cookies
        assert (await client.get("/api/v1/auth/me")).status_code == 401

        completed = await client.post("/api/v1/auth/mfa/verify-login", json={"code": totp(secret)}, headers=headers)
        assert completed.status_code == 200
        assert completed.json()["user"]["id"] == str(user.id)
        assert "mdis_access" in client.cookies
        replayed = await client.post("/api/v1/auth/mfa/verify-login", json={"code": totp(secret)}, headers=headers)
        assert replayed.status_code == 401

        await client.post("/api/v1/auth/logout", headers=await csrf(client))
        headers = await csrf(client)
        pending_again = await client.post("/api/v1/auth/login", json={"email": user.email, "password": "synthetic secure phrase 89!"}, headers=headers)
        assert pending_again.json()["status"] == "pending_mfa"
        recovery_login = await client.post("/api/v1/auth/mfa/verify-login", json={"code": recovery_codes[0]}, headers=headers)
        assert recovery_login.status_code == 200
        async with AsyncSessionLocal() as db:
            persisted = await db.get(User, user.id)
            assert recovery_hash(recovery_codes[0]) not in persisted.recovery_code_hashes


@pytest.mark.asyncio
async def test_mfa_login_verification_is_rate_limited_per_account(monkeypatch):
    monkeypatch.setattr(settings, "auth_rate_limit_per_ip", 100)
    monkeypatch.setattr(settings, "auth_rate_limit_per_account", 1)
    user = await make_user(UserRole.ADMIN, mfa_enabled=True)
    secret = new_totp_secret()
    async with AsyncSessionLocal() as db:
        persisted = await db.get(User, user.id)
        persisted.mfa_secret_encrypted = encrypt_secret(secret)
        await db.commit()

    async with AsyncClient(transport=phase2_transport(), base_url="http://test") as client:
        headers = await csrf(client)
        pending = await client.post("/api/v1/auth/login", json={"email": user.email, "password": "synthetic secure phrase 89!"}, headers=headers)
        assert pending.status_code == 200 and pending.json()["status"] == "pending_mfa"
        first = await client.post("/api/v1/auth/mfa/verify-login", json={"code": "invalid-code-123"}, headers=headers)
        second = await client.post("/api/v1/auth/mfa/verify-login", json={"code": "invalid-code-123"}, headers=headers)
    assert first.status_code == 401
    assert second.status_code == 429


@pytest.mark.asyncio
async def test_remember_me_controls_server_refresh_session_lifetime():
    standard_user = await make_user()
    remembered_user = await make_user()
    async with AsyncClient(transport=phase2_transport(), base_url="http://test") as client:
        headers = await csrf(client)
        standard_response = await client.post(
            "/api/v1/auth/login",
            json={"email": standard_user.email, "password": "synthetic secure phrase 89!", "remember_me": False},
            headers=headers,
        )
        assert standard_response.status_code == 200
        assert "max-age" not in next(cookie for cookie in standard_response.headers.get_list("set-cookie") if cookie.startswith("mdis_refresh="))

        await client.post("/api/v1/auth/logout", headers=headers)
        headers = await csrf(client)
        remembered_response = await client.post(
            "/api/v1/auth/login",
            json={"email": remembered_user.email, "password": "synthetic secure phrase 89!", "remember_me": True},
            headers=headers,
        )
        assert remembered_response.status_code == 200
        assert "max-age=" in next(cookie.casefold() for cookie in remembered_response.headers.get_list("set-cookie") if cookie.startswith("mdis_refresh="))
        headers = await csrf(client)
        rotated_response = await client.post("/api/v1/auth/refresh", headers=headers)
        assert rotated_response.status_code == 200

    async with AsyncSessionLocal() as db:
        standard = await db.scalar(select(RefreshToken).where(RefreshToken.user_id == standard_user.id))
        remembered = await db.scalar(select(RefreshToken).where(RefreshToken.user_id == remembered_user.id).order_by(RefreshToken.created_at.desc()))
        assert standard is not None and standard.remember_me is False
        assert remembered is not None and remembered.remember_me is True
        assert remembered.expires_at - remembered.created_at > standard.expires_at - standard.created_at


@pytest.mark.asyncio
async def test_logout_invalidates_the_access_token_session_family():
    user = await make_user()
    async with AsyncClient(transport=phase2_transport(), base_url="http://test") as client:
        headers = await csrf(client)
        signed_in = await client.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": "synthetic secure phrase 89!"},
            headers=headers,
        )
        assert signed_in.status_code == 200
        assert (await client.get("/api/v1/auth/me")).status_code == 200
        access_token = client.cookies.get("mdis_access")
        headers = await csrf(client)
        logged_out = await client.post("/api/v1/auth/logout", headers=headers)
        assert logged_out.status_code == 204
        replay = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"}
        )
        assert replay.status_code == 401


@pytest.mark.asyncio
async def test_role_change_requires_admin_and_admin_actions_are_audited():
    clinician = await make_user()
    token = create_access_token({"sub": str(clinician.id)})
    async with AsyncClient(transport=phase2_transport(), base_url="http://test", headers={"Authorization": f"Bearer {token}"}) as client:
        response = await client.patch(f"/api/v1/admin/users/{clinician.id}/role", json={"role": "viewer"})
    assert response.status_code == 403
    admin = await make_user(UserRole.ADMIN, mfa_enabled=True)
    encrypted_secret = encrypt_secret(new_totp_secret())
    async with AsyncSessionLocal() as db:
        stored_admin = await db.get(User, admin.id)
        stored_admin.mfa_secret_encrypted = encrypted_secret
        await db.commit()
    admin_token = create_access_token({"sub": str(admin.id)})
    async with AsyncClient(transport=phase2_transport(), base_url="http://test", headers={"Authorization": f"Bearer {admin_token}"}) as client:
        changed = await client.patch(f"/api/v1/admin/users/{clinician.id}/role", json={"role": "viewer"})
    assert changed.status_code == 200
    async with AsyncSessionLocal() as db:
        audit = await db.scalar(select(AuditEvent).where(AuditEvent.action == "ROLE_CHANGED", AuditEvent.resource_id == clinician.id).order_by(AuditEvent.created_at.desc()))
        assert audit and audit.user_id == admin.id and audit.organization_id == admin.organization_id


@pytest.mark.asyncio
async def test_admin_cannot_change_own_role_or_deactivate_own_account():
    admin = await make_user(UserRole.ADMIN, mfa_enabled=True)
    token = create_access_token({"sub": str(admin.id)})
    async with AsyncClient(transport=phase2_transport(), base_url="http://test", headers={"Authorization": f"Bearer {token}"}) as client:
        role_response = await client.patch(
            f"/api/v1/admin/users/{admin.id}/role",
            json={"role": "clinician"},
        )
        deactivate_response = await client.post(f"/api/v1/admin/users/{admin.id}/deactivate")
    assert role_response.status_code == 409
    assert deactivate_response.status_code == 409
    async with AsyncSessionLocal() as db:
        persisted = await db.get(User, admin.id)
        denied = (await db.scalars(select(AuditEvent).where(
            AuditEvent.user_id == admin.id,
            AuditEvent.action == "AUTHZ_DENIED",
        ))).all()
    assert persisted and persisted.role == UserRole.ADMIN and persisted.is_active
    assert len(denied) >= 2




@pytest.mark.asyncio
async def test_admin_invite_is_single_use_and_acceptance_sets_password(monkeypatch):
    admin = await make_user(UserRole.ADMIN, mfa_enabled=True)
    admin.mfa_secret_encrypted = encrypt_secret(new_totp_secret())
    async with AsyncSessionLocal() as db:
        stored = await db.get(User, admin.id)
        stored.mfa_enabled = True
        stored.mfa_secret_encrypted = admin.mfa_secret_encrypted
        await db.commit()
    delivery: list[str] = []

    async def capture(_email: str, _purpose: str, token: str):
        delivery.append(token)
        return True

    monkeypatch.setattr(admin_auth, "send_action_link", capture)
    monkeypatch.setattr(admin_auth, "configured_email_provider", lambda: object())
    monkeypatch.setattr(settings, "public_app_url", "http://localhost:8443")
    token = create_access_token({"sub": str(admin.id)})
    async with AsyncClient(transport=phase2_transport(), base_url="http://test", headers={"Authorization": f"Bearer {token}"}) as client:
        invited_email = f"invited-{uuid.uuid4()}@example.test"
        response = await client.post("/api/v1/admin/invitations", json={"email": invited_email, "full_name": "Synthetic Invitee", "role": "clinician"})
        assert response.status_code == 201
        assert response.json()["email_delivery"] == "queued"
        assert delivery
        headers = await csrf(client)
        accepted = await client.post("/api/v1/admin/invitations/accept", json={"token": delivery[0], "password": "new account password 932! secure"}, headers=headers)
        assert accepted.status_code == 200
        replay = await client.post("/api/v1/admin/invitations/accept", json={"token": delivery[0], "password": "replay account password 932! secure"}, headers=headers)
        assert replay.status_code == 400
    async with AsyncSessionLocal() as db:
        invited = await db.scalar(select(User).where(User.email == invited_email))
        assert invited and invited.is_active and not invited.pending_approval and invited.password_hash


@pytest.mark.asyncio
async def test_admin_failures_alert_without_account_lockout():
    admin = await make_user(UserRole.ADMIN)
    async with AsyncClient(transport=phase2_transport(), base_url="http://test") as client:
        headers = await csrf(client)
        for _ in range(settings.auth_lockout_attempts + 1):
            response = await client.post("/api/v1/auth/login", json={"email": admin.email, "password": "incorrect synthetic password"}, headers=headers)
            assert response.status_code == 401
    async with AsyncSessionLocal() as db:
        stored = await db.get(User, admin.id)
        assert stored.locked_until is None


@pytest.mark.asyncio
async def test_clinician_lockout_is_progressive_and_not_extended_by_locked_attempts():
    user = await make_user()
    async with AsyncClient(transport=phase2_transport(), base_url="http://test") as client:
        headers = await csrf(client)
        for _ in range(settings.auth_lockout_attempts):
            response = await client.post("/api/v1/auth/login", json={"email": user.email, "password": "wrong synthetic password"}, headers=headers)
            assert response.status_code == 401
    async with AsyncSessionLocal() as db:
        locked = await db.get(User, user.id)
        locked_until = locked.locked_until
        assert locked_until is not None
        assert locked_until > datetime.now(timezone.utc) + timedelta(minutes=settings.auth_lockout_minutes - 1)
    async with AsyncClient(transport=phase2_transport(), base_url="http://test") as client:
        headers = await csrf(client)
        response = await client.post("/api/v1/auth/login", json={"email": user.email, "password": "synthetic secure phrase 89!"}, headers=headers)
        assert response.status_code == 401
    async with AsyncSessionLocal() as db:
        locked = await db.get(User, user.id)
        assert locked.locked_until == locked_until


def test_wildcard_cors_configuration_is_rejected(monkeypatch):
    from app.security.auth import validate_jwt_configuration

    monkeypatch.setattr(settings, "cors_origins", "*")
    with pytest.raises(RuntimeError, match="explicit origin allowlist"):
        validate_jwt_configuration()


@pytest.mark.asyncio
async def test_registration_modes_reject_disabled_and_allow_pending_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "registration_mode", "disabled")
    email = f"pending-{uuid.uuid4()}@example.test"
    async with AsyncClient(transport=phase2_transport(), base_url="http://test") as client:
        headers = await csrf(client)
        payload = {
            "work_email": email,
            "full_name": "Synthetic Pending",
            "organization_request_name": "Synthetic Clinic",
            "professional_role": "doctor",
            "license_or_certification_number": "SYN-12345",
            "license_type": "medical",
            "password": "random registration phrase 672!",
            "confirm_password": "random registration phrase 672!",
            "accepted_terms": True,
        }
        disabled = await client.post("/api/v1/auth/register", json=payload, headers=headers)
        assert disabled.status_code == 404
        monkeypatch.setattr(settings, "registration_mode", "approval")
        monkeypatch.setattr(auth_router, "email_delivery_available", lambda: True)
        from app.services import verification_codes
        monkeypatch.setattr(verification_codes, "email_delivery_available", lambda: True)
        monkeypatch.setattr(verification_codes, "_deliver_verification_code", lambda *_args, **_kwargs: None)
        registered = await client.post("/api/v1/auth/register", json=payload, headers=headers)
        assert registered.status_code == 202
        pending_login = await client.post("/api/v1/auth/login", json={"email": email, "password": "random registration phrase 672!"}, headers=headers)
        assert pending_login.status_code == 200
        assert pending_login.json()["status"] == "pending_email_verification"
        assert "mdis_access" not in pending_login.cookies
    async with AsyncSessionLocal() as db:
        pending = await db.scalar(select(User).where(User.email == email))
        assert pending and pending.pending_approval and not pending.is_active
        assert pending.registration_status == "pending_email_verification"


@pytest.mark.asyncio
async def test_security_headers_and_request_id_are_present():
    async with AsyncClient(transport=phase2_transport(), base_url="http://test") as client:
        response = await client.get("/api/v1/health")
    assert response.headers.get("x-request-id")
    assert "frame-ancestors 'none'" in response.headers.get("content-security-policy", "")
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("referrer-policy") == "no-referrer"
    assert response.headers.get("permissions-policy")


def secrets_token() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex
