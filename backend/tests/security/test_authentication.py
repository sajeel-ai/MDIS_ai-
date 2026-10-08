"""Authentication endpoint regression tests."""

import uuid
import base64
import hashlib
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import jwt
from httpx import ASGITransport, AsyncClient

from app.db import get_db
from app.main import app
from app.models import User, UserRole
from app.models.organization import DEFAULT_ORGANIZATION_ID
from app.security.auth import create_access_token, hash_password, password_needs_rehash, validate_jwt_configuration, verify_password, validate_password_policy
from app.config import settings


@pytest.fixture
def auth_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="clinician@example.test",
        display_name="Test Clinician",
        role=UserRole.CLINICIAN,
        organization_id=DEFAULT_ORGANIZATION_ID,
        is_active=True,
        password_hash=hash_password("correct horse battery staple"),
    )


@pytest.fixture
def mock_db(auth_user, monkeypatch):
    session = AsyncMock()
    session.add = MagicMock()
    session.info = {}
    result = MagicMock()
    result.scalars.return_value.first.return_value = auth_user
    session.execute.return_value = result

    async def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr("app.routers.auth.enforce_auth_rate_limit", AsyncMock())
    yield session
    app.dependency_overrides.clear()


def test_auth_bypass_is_rejected_outside_development(monkeypatch):
    monkeypatch.setattr(settings, "auth_disabled", True)
    monkeypatch.setattr(settings, "app_env", "production")
    with pytest.raises(RuntimeError, match="only be enabled in development"):
        validate_jwt_configuration()


def test_auth_bypass_emits_warning_in_development(monkeypatch, caplog):
    monkeypatch.setattr(settings, "auth_disabled", True)
    monkeypatch.setattr(settings, "app_env", "development")
    validate_jwt_configuration()
    assert "AUTH_DISABLED is set in development" in caplog.text


@pytest.mark.parametrize(
    ("setting", "value", "message"),
    [
        ("jwt_secret_key", "cognate-dev-secret-key-change-in-production-1234567890", "JWT_SECRET_KEY"),
        ("auth_cookie_secure", False, "AUTH_COOKIE_SECURE"),
        ("debug", True, "DEBUG"),
    ],
)
def test_production_startup_refuses_unsafe_auth_configuration(monkeypatch, setting, value, message):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "auth_disabled", False)
    monkeypatch.setattr(settings, "jwt_secret_key", "private-test-signing-key-with-length-over-32")
    monkeypatch.setattr(settings, "auth_cookie_secure", True)
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(settings, setting, value)
    monkeypatch.setattr(settings, "password_blocklist_file", "")
    with pytest.raises(RuntimeError, match=message):
        validate_jwt_configuration()


def test_production_startup_refuses_frontend_bypass_flag(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "auth_disabled", False)
    monkeypatch.setattr(settings, "jwt_secret_key", "private-test-signing-key-with-length-over-32")
    monkeypatch.setattr(settings, "auth_cookie_secure", True)
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(settings, "password_blocklist_file", "missing-test-blocklist.txt")
    monkeypatch.setenv("VITE_AUTH_BYPASS", "true")
    with pytest.raises(RuntimeError, match="VITE_AUTH_BYPASS"):
        validate_jwt_configuration()


def test_environment_production_marker_cannot_be_overridden_by_development_app_env(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "auth_disabled", True)
    with pytest.raises(RuntimeError, match="only be enabled in development"):
        validate_jwt_configuration()


def test_production_startup_refuses_mock_processing_providers(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "auth_disabled", False)
    monkeypatch.setattr(settings, "jwt_secret_key", "private-test-signing-key-with-length-over-32")
    monkeypatch.setattr(settings, "auth_cookie_secure", True)
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(settings, "ocr_provider", "mock")
    monkeypatch.setattr(settings, "extraction_provider", "local")
    with pytest.raises(RuntimeError, match="Mock OCR and extraction providers"):
        validate_jwt_configuration()


async def request_me(token: str | None = None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.get("/api/v1/auth/me", headers=headers)


@pytest.mark.asyncio
async def test_missing_token_is_rejected(mock_db):
    response = await request_me()
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    mock_db.add.assert_called_once()
    assert mock_db.add.call_args.args[0].action == "AUTHZ_DENIED"
    assert mock_db.add.call_args.args[0].metadata_ == {"action": "AUTHZ_DENIED", "resource_id": None, "organization_id": None}


@pytest.mark.asyncio
async def test_invalid_token_is_rejected(mock_db):
    response = await request_me("not-a-valid-jwt")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_expired_token_is_rejected(mock_db, auth_user):
    token = create_access_token(
        {"sub": str(auth_user.id)}, expires_delta=timedelta(seconds=-1)
    )
    response = await request_me(token)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_jwt_none_algorithm_and_wrong_audience_are_rejected(mock_db, auth_user):
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    claims = {
        "sub": str(auth_user.id),
        "sid": str(uuid.uuid4()),
        "jti": "synthetic-token-id",
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    unsigned = jwt.encode(claims, key="", algorithm="none")
    wrong_audience = jwt.encode(
        {**claims, "aud": "untrusted-client"},
        settings.jwt_secret_key,
        algorithm="HS256",
    )
    assert (await request_me(unsigned)).status_code == 401
    assert (await request_me(wrong_audience)).status_code == 401


@pytest.mark.asyncio
async def test_valid_token_resolves_database_user(mock_db, auth_user):
    token = create_access_token({"sub": str(auth_user.id)})
    response = await request_me(token)
    assert response.status_code == 200
    assert response.json() == {
        "id": str(auth_user.id),
        "email": auth_user.email,
        "display_name": auth_user.display_name,
        "role": auth_user.role,
    }


@pytest.mark.asyncio
async def test_change_password_validates_current_password_and_revokes_session(mock_db, auth_user):
    token = create_access_token({"sub": str(auth_user.id)})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/api/v1/auth/csrf")
        headers = {"Authorization": f"Bearer {token}", "X-CSRF-Token": client.cookies.get("mdis_csrf")}
        response = await client.post("/api/v1/auth/change-password", headers=headers, json={
            "current_password": "correct horse battery staple",
            "new_password": "synthetic replacement phrase 2026",
        })
    assert response.status_code == 200
    assert response.json()["message"] == "Password changed. Sign in again."
    assert response.headers["cache-control"] == "no-store, private"
    assert verify_password("synthetic replacement phrase 2026", auth_user.password_hash)
    assert response.headers.get_list("set-cookie")


@pytest.mark.asyncio
async def test_change_password_rejects_wrong_current_password(mock_db, auth_user):
    token = create_access_token({"sub": str(auth_user.id)})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/api/v1/auth/csrf")
        headers = {"Authorization": f"Bearer {token}", "X-CSRF-Token": client.cookies.get("mdis_csrf")}
        response = await client.post("/api/v1/auth/change-password", headers=headers, json={
            "current_password": "wrong current password",
            "new_password": "synthetic replacement phrase 2026",
        })
    assert response.status_code == 401
    assert verify_password("correct horse battery staple", auth_user.password_hash)


@pytest.mark.asyncio
async def test_inactive_user_is_rejected(mock_db, auth_user):
    auth_user.is_active = False
    token = create_access_token({"sub": str(auth_user.id)})
    response = await request_me(token)
    assert response.status_code == 401


def test_password_policy_has_length_identity_and_blocklist_checks():
    validate_password_policy("correct horse battery staple", email="clinician@example.test", full_name="Test Clinician")
    with pytest.raises(ValueError, match="12"):
        validate_password_policy("short", email="person@example.test")
    with pytest.raises(ValueError, match="email or name"):
        validate_password_policy("clinician@example.test safe", email="clinician@example.test")
    with pytest.raises(ValueError, match="blocklist"):
        validate_password_policy("123456789012", email="person@example.test")


@pytest.mark.asyncio
async def test_login_issues_token_for_active_account(mock_db, auth_user):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        csrf_response = await client.get("/api/v1/auth/csrf")
        csrf = csrf_response.cookies.get("mdis_csrf")
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": auth_user.email, "password": "correct horse battery staple"},
            headers={"X-CSRF-Token": csrf},
        )
    assert response.status_code == 200
    assert response.json()["user"]["email"] == auth_user.email
    assert "access_token" not in response.json()
    assert "mdis_access=" in response.headers["set-cookie"]
    assert "httponly" in response.headers["set-cookie"].lower()


@pytest.mark.asyncio
async def test_legacy_password_is_rehashed_after_successful_login(mock_db, auth_user):
    salt = b"synthetic-test-salt"
    digest = hashlib.scrypt(b"correct horse battery staple", salt=salt, n=2**14, r=8, p=1)
    encode = lambda value: base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")
    auth_user.password_hash = f"scrypt$16384$8$1${encode(salt)}${encode(digest)}"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/api/v1/auth/csrf")
        csrf = client.cookies.get("mdis_csrf")
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": auth_user.email, "password": "correct horse battery staple"},
            headers={"X-CSRF-Token": csrf},
        )
    assert response.status_code == 200
    assert auth_user.password_hash.startswith("$argon2id$")
    assert auth_user.password_changed_at is not None


@pytest.mark.asyncio
async def test_unknown_email_and_wrong_password_have_identical_login_errors(mock_db, auth_user):
    found = MagicMock()
    found.scalars.return_value.first.return_value = auth_user
    missing = MagicMock()
    missing.scalars.return_value.first.return_value = None
    mock_db.execute.side_effect = [found, missing]
    responses = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        csrf_response = await client.get("/api/v1/auth/csrf")
        csrf = csrf_response.cookies.get("mdis_csrf")
        for email, password in ((auth_user.email, "incorrect password"), ("missing@example.test", "incorrect password")):
            result = await client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": password},
                headers={"X-CSRF-Token": csrf},
            )
            responses.append((result.status_code, result.json()))
    assert responses[0] == responses[1] == (401, {"detail": "Incorrect email or password"})


@pytest.mark.asyncio
async def test_login_rejects_missing_csrf(mock_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/auth/login", json={"email": "a@example.test", "password": "not a real password"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_login_rejects_unknown_request_fields(mock_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        csrf_response = await client.get("/api/v1/auth/csrf")
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "person@example.test", "password": "a synthetic passphrase", "role": "admin"},
            headers={"X-CSRF-Token": csrf_response.cookies.get("mdis_csrf")},
        )
    assert response.status_code == 422


def test_password_hash_is_argon2id_and_legacy_scrypt_requires_rehash():
    encoded = hash_password("synthetic secure passphrase")
    assert encoded.startswith("$argon2id$")
    assert verify_password("synthetic secure passphrase", encoded)
    assert not verify_password("wrong passphrase", encoded)
    assert password_needs_rehash("scrypt$16384$8$1$c2FsdA$ZGlnZXN0")


@pytest.mark.asyncio
async def test_refresh_rotates_token_and_keeps_it_out_of_json(mock_db, auth_user):
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    old = SimpleNamespace(
        id=uuid.uuid4(), user_id=auth_user.id, family_id=uuid.uuid4(), token_hash="old-hash",
        expires_at=now + timedelta(days=1), revoked_at=None, replaced_by_id=None, remember_me=False,
    )
    replacement = SimpleNamespace(id=uuid.uuid4())
    mock_db.scalar.side_effect = [old, replacement]
    mock_db.get.return_value = auth_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/api/v1/auth/csrf")
        csrf = client.cookies.get("mdis_csrf")
        client.cookies.set("mdis_refresh", "synthetic-refresh-secret", path="/api/v1/auth")
        response = await client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200
    assert old.revoked_at is not None
    assert old.replaced_by_id == replacement.id
    assert "mdis_access=" in response.headers["set-cookie"]
    assert "access_token" not in response.json()


@pytest.mark.asyncio
async def test_reuse_of_rotated_refresh_token_revokes_family(mock_db):
    old = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4(), family_id=uuid.uuid4(), revoked_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))
    mock_db.scalar.return_value = old
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/api/v1/auth/csrf")
        csrf = client.cookies.get("mdis_csrf")
        client.cookies.set("mdis_refresh", "reused-token", path="/api/v1/auth")
        response = await client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 401
    mock_db.execute.assert_awaited_once()
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_expired_refresh_token_is_rejected(mock_db):
    expired = SimpleNamespace(
        id=uuid.uuid4(), user_id=uuid.uuid4(), family_id=uuid.uuid4(),
        expires_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc) - timedelta(seconds=1),
        revoked_at=None,
    )
    mock_db.scalar.return_value = expired
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        csrf_response = await client.get("/api/v1/auth/csrf")
        csrf = csrf_response.cookies.get("mdis_csrf")
        client.cookies.set("mdis_refresh", "synthetic-expired-refresh", path="/api/v1/auth")
        response = await client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 401
    assert expired.revoked_at is not None
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_logout_revokes_token_family_and_clears_cookies(mock_db):
    token_row = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4(), family_id=uuid.uuid4())
    mock_db.scalar.return_value = token_row
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/api/v1/auth/csrf")
        csrf = client.cookies.get("mdis_csrf")
        client.cookies.set("mdis_refresh", "synthetic-refresh-secret", path="/api/v1/auth")
        response = await client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 204
    mock_db.execute.assert_awaited_once()
    mock_db.commit.assert_awaited_once()
    assert "mdis_refresh" in response.headers.get("set-cookie", "")
