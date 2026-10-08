"""Password hashing, JWT validation, and authenticated-user resolution."""

import base64
import hashlib
import hmac
import logging
import os
from pathlib import Path
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.models import RefreshToken, User, UserRole
from app.services.audit_service import record_audit_event

INSECURE_JWT_SECRETS = {"secret", "changeme", "change-this-in-production-1234567890"}
JWT_ALGORITHM = "HS256"
ACCESS_COOKIE = "mdis_access"
REFRESH_COOKIE = "mdis_refresh"
CSRF_COOKIE = "mdis_csrf"
logger = logging.getLogger(__name__)
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.api_prefix}/auth/login", auto_error=False
)
_password_hasher = PasswordHasher(time_cost=2, memory_cost=19_456, parallelism=1)
_dummy_password_hash = _password_hasher.hash(secrets.token_urlsafe(32))
DUMMY_PASSWORD_HASH = _dummy_password_hash


def validate_jwt_configuration() -> None:
    """Fail closed when an unsafe auth or production configuration is selected."""
    environment_values = [settings.app_env.strip().lower()]
    if settings.environment and settings.environment.strip():
        environment_values.append(settings.environment.strip().lower())
    is_development = all(value == "development" for value in environment_values)
    if settings.auth_disabled and not is_development:
        raise RuntimeError("AUTH_DISABLED may only be enabled in development")
    if os.getenv("VITE_AUTH_BYPASS", "").strip().lower() == "true" and not is_development:
        raise RuntimeError("VITE_AUTH_BYPASS must not be enabled outside development")
    if settings.auth_disabled:
        logger.warning("AUTH_DISABLED is set in development; authentication remains required")
    if settings.jwt_algorithm != JWT_ALGORITHM:
        raise RuntimeError("JWT_ALGORITHM must remain pinned to HS256")
    if (
        len(settings.jwt_secret_key) < 32
        or settings.jwt_secret_key.strip().casefold() in INSECURE_JWT_SECRETS
        or "cognate-dev-secret-key" in settings.jwt_secret_key.casefold()
        or "change-this" in settings.jwt_secret_key.casefold()
    ):
        raise RuntimeError("JWT_SECRET_KEY must be a private value of at least 32 characters")
    if not settings.jwt_issuer.strip() or not settings.jwt_audience.strip():
        raise RuntimeError("JWT issuer and audience must be configured")
    origins = settings.cors_origins_list
    if not origins or any(origin == "*" for origin in origins):
        raise RuntimeError("CORS_ORIGINS must be a non-empty explicit origin allowlist")
    if not is_development:
        if not settings.auth_cookie_secure:
            raise RuntimeError("AUTH_COOKIE_SECURE must be true outside development")
        if settings.debug:
            raise RuntimeError("DEBUG must be false outside development")
        if settings.ocr_provider.strip().lower() == "mock" or settings.extraction_provider.strip().lower() == "mock":
            raise RuntimeError("Mock OCR and extraction providers may only be used in development")
        try:
            from app.security.mfa import _key
            _key()
        except RuntimeError as exc:
            raise RuntimeError("AUTH_ENCRYPTION_KEY must be configured outside development") from exc
        if not settings.password_blocklist_file or not Path(settings.password_blocklist_file).is_file():
            raise RuntimeError("PASSWORD_BLOCKLIST_FILE must point to a readable compromised-password blocklist outside development")
        try:
            if not any(
                line.strip() and not line.lstrip().startswith("#")
                for line in Path(settings.password_blocklist_file).read_text(encoding="utf-8").splitlines()
            ):
                raise RuntimeError("PASSWORD_BLOCKLIST_FILE must contain password entries outside development")
        except OSError as exc:
            raise RuntimeError("PASSWORD_BLOCKLIST_FILE must be readable outside development") from exc


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    validate_jwt_configuration()
    now = datetime.now(timezone.utc)
    expiry = expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes)
    if expiry > timedelta(minutes=15):
        raise ValueError("Access token lifetime cannot exceed 15 minutes")
    claims = {
        **data,
        "iat": now,
        "exp": now + expiry,
        "jti": secrets.token_urlsafe(24),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    return jwt.encode(claims, settings.jwt_secret_key, algorithm=JWT_ALGORITHM)


def hash_password(password: str) -> str:
    """Create an Argon2id hash using at least 19 MiB and two iterations."""
    return _password_hasher.hash(password)


def verify_password(password: str, encoded: Optional[str]) -> bool:
    """Verify Argon2id hashes and legacy scrypt hashes during migration."""
    if not encoded:
        return False
    if encoded.startswith("$argon2id$"):
        try:
            return _password_hasher.verify(encoded, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
    try:
        scheme, n, r, p, salt_text, digest_text = encoded.split("$")
        if scheme != "scrypt":
            return False
        decode = lambda value: base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        salt, expected = decode(salt_text), decode(digest_text)
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def password_needs_rehash(encoded: str | None) -> bool:
    if not encoded or not encoded.startswith("$argon2id$"):
        return True
    try:
        return _password_hasher.check_needs_rehash(encoded)
    except (VerificationError, InvalidHashError):
        return True


def validate_password_policy(password: str, *, email: str = "", full_name: str = "") -> None:
    if len(password) < 12 or len(password) > 1024:
        raise ValueError("Password must be between 12 and 1024 characters")
    folded = password.casefold()
    identity_parts = [email.split("@", 1)[0], *full_name.split()]
    if any(len(part.strip()) >= 3 and part.strip().casefold() in folded for part in identity_parts):
        raise ValueError("Password must not contain your email or name")
    configured = {item.strip().casefold() for item in settings.password_blocklist.split(",") if item.strip()}
    if settings.password_blocklist_file:
        try:
            configured.update(
                line.strip().casefold()
                for line in Path(settings.password_blocklist_file).read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            )
        except OSError as exc:
            raise RuntimeError("Configured password blocklist could not be read") from exc
    if folded in configured:
        raise ValueError("Choose a password that is not on the common or compromised password blocklist")


def unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def verify_csrf(request: Request) -> None:
    cookie_value = request.cookies.get(CSRF_COOKIE)
    header_value = request.headers.get("X-CSRF-Token")
    if not cookie_value or not header_value or not hmac.compare_digest(cookie_value, header_value):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve identity only from a valid JWT cookie or bearer credential."""
    cookie_token = request.cookies.get(ACCESS_COOKIE)
    credential = token or cookie_token
    if not credential:
        await record_audit_event(db, action="AUTHZ_DENIED", request=request)
        await db.commit()
        raise unauthorized()
    if cookie_token and not token and request.method.upper() not in {"GET", "HEAD", "OPTIONS"}:
        verify_csrf(request)

    try:
        payload = jwt.decode(
            credential,
            settings.jwt_secret_key,
            algorithms=[JWT_ALGORITHM],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["exp", "iat", "sub", "jti", "iss", "aud"]},
        )
        user_id = uuid.UUID(payload["sub"])
        family_id = uuid.UUID(payload["sid"]) if payload.get("sid") else None
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        await record_audit_event(db, action="AUTHZ_DENIED", request=request)
        await db.commit()
        raise unauthorized()

    db.info["scope_required"] = True
    db.info["allow_unscoped_user_lookup"] = True
    try:
        result = await db.execute(select(User).where(User.id == user_id))
    finally:
        db.info.pop("allow_unscoped_user_lookup", None)
    user = result.scalars().first()
    if user is None or not user.is_active or user.organization_id is None:
        await record_audit_event(db, action="AUTHZ_DENIED", user_id=user_id, request=request)
        await db.commit()
        raise unauthorized()
    db.info["organization_id"] = user.organization_id

    # A privileged role never receives API access before MFA is enrolled.
    if user.role in {UserRole.ADMIN, UserRole.OPERATOR} and not user.mfa_enabled:
        await record_audit_event(db, action="AUTHZ_DENIED", user_id=user.id, organization_id=user.organization_id, request=request)
        await db.commit()
        raise unauthorized("MFA enrollment required")

    if family_id:
        active_session = await db.scalar(
            select(RefreshToken.id).where(
                RefreshToken.family_id == family_id,
                RefreshToken.user_id == user.id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > datetime.now(timezone.utc),
            ).limit(1)
        )
        if active_session is None:
            await record_audit_event(db, action="AUTHZ_DENIED", user_id=user.id, organization_id=user.organization_id, request=request)
            await db.commit()
            raise unauthorized()
    return user
