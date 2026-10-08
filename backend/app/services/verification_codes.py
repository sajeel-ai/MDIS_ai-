"""Hashed, short-lived email verification codes for auth workflows."""

import asyncio
import hashlib
import hmac
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from re import fullmatch

from fastapi import BackgroundTasks, HTTPException, Request
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import AuthVerificationCode, User
from app.services.audit_service import record_audit_event
from app.services.auth_rate_limit import enforce_auth_rate_limit
from app.services.email_provider import email_delivery_available, send_verification_code


class VerificationCodePurpose(StrEnum):
    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"
    MFA_FALLBACK = "mfa_fallback"


CODE_TTL = timedelta(minutes=10)
_DUMMY_CODE_HASH = "0" * 64


def _hash_code(row_id: uuid.UUID, purpose: str, code: str) -> str:
    key = settings.auth_encryption_key or settings.jwt_secret_key
    material = f"{row_id}:{purpose}:{code}".encode("utf-8")
    return hmac.new(key.encode("utf-8"), material, hashlib.sha256).hexdigest()


async def _deliver_verification_code(email: str, purpose: str, code: str) -> None:
    try:
        await send_verification_code(email, purpose, code)
    except Exception:
        # Provider exceptions may contain recipient, code, or message data; never log them.
        return


def _eligible_for_purpose(user: User, purpose: VerificationCodePurpose) -> bool:
    if purpose is VerificationCodePurpose.RESET_PASSWORD:
        return user.is_active
    if purpose is VerificationCodePurpose.VERIFY_EMAIL:
        return user.registration_status == "pending_email_verification" and not user.email_verified
    return user.is_active and user.mfa_enabled


async def request_verification_code(
    db: AsyncSession,
    request: Request,
    background: BackgroundTasks,
    email: str,
    purpose: VerificationCodePurpose,
) -> None:
    """Issue a code if eligible, but provide no account-dependent result to the caller."""
    started = time.monotonic()
    if not email_delivery_available():
        raise HTTPException(status_code=503, detail="Email delivery is not configured")
    normalized_email = email.strip().lower()
    purpose_value = purpose.value
    await enforce_auth_rate_limit(
        request,
        db,
        f"verification_code_request:{purpose_value}",
        normalized_email,
    )
    now = datetime.now(timezone.utc)
    db.info["allow_unscoped_user_lookup"] = True
    try:
        user = await db.scalar(select(User).where(User.email == normalized_email).with_for_update())
    finally:
        db.info.pop("allow_unscoped_user_lookup", None)

    issued_row: AuthVerificationCode | None = None
    raw_code: str | None = None
    if user is not None and _eligible_for_purpose(user, purpose):
        since_day = now - timedelta(days=1)
        daily_count = await db.scalar(
            select(func.count()).select_from(AuthVerificationCode).where(
                AuthVerificationCode.user_id == user.id,
                AuthVerificationCode.purpose == purpose_value,
                AuthVerificationCode.created_at >= since_day,
            )
        )
        latest = await db.scalar(
            select(AuthVerificationCode)
            .where(
                AuthVerificationCode.user_id == user.id,
                AuthVerificationCode.purpose == purpose_value,
            )
            .order_by(AuthVerificationCode.created_at.desc())
            .limit(1)
        )
        cooldown_active = bool(
            latest
            and latest.created_at
            and now - latest.created_at < timedelta(seconds=settings.email_code_cooldown_seconds)
        )
        if not cooldown_active and (daily_count or 0) < settings.email_code_daily_limit:
            await db.execute(
                update(AuthVerificationCode)
                .where(
                    AuthVerificationCode.user_id == user.id,
                    AuthVerificationCode.purpose == purpose_value,
                    AuthVerificationCode.is_used.is_(False),
                    AuthVerificationCode.invalidated_at.is_(None),
                )
                .values(invalidated_at=now)
            )
            raw_code = f"{secrets.randbelow(1_000_000):06d}"
            issued_row = AuthVerificationCode(
                user_id=user.id,
                purpose=purpose_value,
                code_hash="0" * 64,
                expires_at=now + CODE_TTL,
            )
            db.add(issued_row)
            await db.flush()
            issued_row.code_hash = _hash_code(issued_row.id, purpose_value, raw_code)

    await record_audit_event(
        db,
        action="CODE_REQUESTED",
        user_id=user.id if user else None,
        organization_id=user.organization_id if user else None,
        resource_type="auth_verification_code" if issued_row else None,
        resource_id=issued_row.id if issued_row else None,
        request=request,
    )
    await db.commit()
    if user is not None and raw_code is not None:
        background.add_task(_deliver_verification_code, user.email, purpose_value, raw_code)

    remaining = settings.auth_enumeration_min_response_ms / 1000 - (time.monotonic() - started)
    if remaining > 0:
        await asyncio.sleep(remaining)


async def verify_verification_code(
    db: AsyncSession,
    request: Request,
    email: str,
    purpose: VerificationCodePurpose,
    code: str,
) -> bool:
    """Check a code once; wrong attempts are counted and the fifth locks it."""
    started = time.monotonic()
    normalized_email = email.strip().lower()
    purpose_value = purpose.value
    await enforce_auth_rate_limit(
        request,
        db,
        f"verification_code_verify:{purpose_value}",
        normalized_email,
    )
    now = datetime.now(timezone.utc)
    db.info["allow_unscoped_user_lookup"] = True
    try:
        user = await db.scalar(select(User).where(User.email == normalized_email))
    finally:
        db.info.pop("allow_unscoped_user_lookup", None)

    candidate = code if fullmatch(r"\d{6}", code or "") else "000000"
    row = None
    if user is not None:
        row = await db.scalar(
            select(AuthVerificationCode)
            .where(
                AuthVerificationCode.user_id == user.id,
                AuthVerificationCode.purpose == purpose_value,
                AuthVerificationCode.is_used.is_(False),
                AuthVerificationCode.invalidated_at.is_(None),
                AuthVerificationCode.expires_at > now,
            )
            .order_by(AuthVerificationCode.created_at.desc())
            .limit(1)
            .with_for_update()
        )

    expected = row.code_hash if row else _DUMMY_CODE_HASH
    actual = _hash_code(row.id, purpose_value, candidate) if row else hmac.new(
        (settings.auth_encryption_key or settings.jwt_secret_key).encode("utf-8"),
        f"unknown:{purpose_value}:{candidate}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    matches = hmac.compare_digest(expected, actual)
    valid_format = fullmatch(r"\d{6}", code or "") is not None

    if row is not None and matches and valid_format and _eligible_for_purpose(user, purpose):
        row.is_used = True
        await record_audit_event(
            db,
            action="CODE_VERIFIED",
            user_id=user.id,
            organization_id=user.organization_id,
            resource_type="auth_verification_code",
            resource_id=row.id,
            request=request,
        )
        await db.commit()
        return True

    if row is not None:
        row.attempts += 1
        if row.attempts >= settings.email_code_max_attempts:
            row.invalidated_at = now
            await record_audit_event(
                db,
                action="CODE_LOCKED",
                user_id=user.id,
                organization_id=user.organization_id,
                resource_type="auth_verification_code",
                resource_id=row.id,
                request=request,
            )
    await record_audit_event(
        db,
        action="CODE_FAILED",
        user_id=user.id if user else None,
        organization_id=user.organization_id if user else None,
        resource_type="auth_verification_code" if row else None,
        resource_id=row.id if row else None,
        request=request,
    )
    await db.commit()
    remaining = settings.auth_enumeration_min_response_ms / 1000 - (time.monotonic() - started)
    if remaining > 0:
        await asyncio.sleep(remaining)
    return False
