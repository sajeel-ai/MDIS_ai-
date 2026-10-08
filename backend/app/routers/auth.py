"""Cookie-based login, logout, refresh, CSRF bootstrap, and current-user APIs."""

import hashlib
import asyncio
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.dependencies.permissions import require_roles
from app.models import AuthActionToken, AuthVerificationCode, Organization, RefreshToken, RegistrationStatus, User, UserRole
from app.models.organization import DEFAULT_ORGANIZATION_ID
from app.security.auth import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    DUMMY_PASSWORD_HASH,
    REFRESH_COOKIE,
    create_access_token,
    get_current_user,
    hash_password,
    password_needs_rehash,
    unauthorized,
    validate_password_policy,
    verify_csrf,
    verify_password,
)
from app.services.audit_service import record_audit_event
from app.services.auth_rate_limit import enforce_auth_rate_limit
from app.services.email_provider import email_delivery_available, send_password_changed_notice, send_account_notice
from app.services.email_templates import EmailTemplate
from app.services.verification_codes import VerificationCodePurpose, request_verification_code, verify_verification_code
from app.security.mfa import decrypt_secret, encrypt_secret, new_recovery_codes, new_totp_secret, provisioning_uri, recovery_hash, verify_totp

router = APIRouter(prefix="/auth", tags=["authentication"])
ACCESS_SECONDS = min(settings.jwt_access_token_expire_minutes, 15) * 60
REFRESH_SECONDS = min(settings.refresh_token_expire_days, 7) * 24 * 60 * 60
SESSION_SECONDS = min(settings.auth_session_expire_hours, 168) * 60 * 60
MFA_PENDING_COOKIE = "mdis_mfa_pending"


async def _issue_action_token(db: AsyncSession, purpose: str, user_id: uuid.UUID | None, *, minutes: int) -> str:
    raw = secrets.token_urlsafe(32)
    db.add(AuthActionToken(
        purpose=purpose, user_id=user_id,
        token_hash=_token_hash(raw),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=minutes),
    ))
    await db.flush()
    return raw


async def _find_action_token(db: AsyncSession, purpose: str, raw: str) -> AuthActionToken | None:
    return await db.scalar(
        select(AuthActionToken).where(
            AuthActionToken.purpose == purpose,
            AuthActionToken.token_hash == _token_hash(raw),
            AuthActionToken.used_at.is_(None),
            AuthActionToken.expires_at > datetime.now(timezone.utc),
        ).with_for_update()
    )


class ForgotPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class VerificationCodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=256)
    purpose: Literal["verify_email", "reset_password"]

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    grant: str = Field(min_length=20, max_length=256)
    new_password: str = Field(min_length=12, max_length=1024)
    confirm_password: str = Field(min_length=12, max_length=1024)

    @model_validator(mode="after")
    def validate_passwords_match(self):
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class VerifyResetCodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=256)
    code: str = Field(min_length=1, max_length=32)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class MFARequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=6, max_length=64)


class RegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    work_email: str = Field(min_length=3, max_length=256, validation_alias=AliasChoices("work_email", "email"))
    full_name: str = Field(min_length=1, max_length=128)
    organization_id: uuid.UUID | None = None
    organization_request_name: str | None = Field(default=None, min_length=2, max_length=128)
    professional_role: Literal["doctor", "lab_technician", "other"]
    license_or_certification_number: str | None = Field(default=None, max_length=128)
    license_type: str | None = Field(default=None, max_length=64)
    phone: str | None = Field(default=None, max_length=32)
    password: str = Field(min_length=12, max_length=1024)
    confirm_password: str = Field(min_length=12, max_length=1024)
    accepted_terms: Literal[True]

    @field_validator("work_email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or any(character.isspace() for character in normalized):
            raise ValueError("Invalid email")
        return normalized

    @field_validator("full_name", "organization_request_name", "license_or_certification_number", "license_type", "phone")
    @classmethod
    def trim_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @model_validator(mode="after")
    def validate_registration(self):
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        if bool(self.organization_id) == bool(self.organization_request_name):
            raise ValueError("Select an organization or request to join by name")
        if bool(self.license_or_certification_number) != bool(self.license_type):
            raise ValueError("License number and license type must be provided together")
        return self


class VerifyEmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=256)
    code: str = Field(min_length=1, max_length=32)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=12, max_length=1024)


async def csrf_protect(request: Request) -> None:
    verify_csrf(request)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=256)
    password: str = Field(min_length=1, max_length=1024)
    otp: str | None = Field(default=None, min_length=6, max_length=6)
    recovery_code: str | None = Field(default=None, min_length=8, max_length=64)
    remember_me: bool = False

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or any(character.isspace() for character in normalized):
            raise ValueError("Enter a valid email address")
        return normalized


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    email: str
    display_name: str | None
    role: str


class LoginResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: UserResponse | None = None
    status: Literal["pending_mfa"] | RegistrationStatus | None = None
    message: str | None = None
    rejection_reason: str | None = None
    mfa_required: bool = False


def _token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("ascii")).hexdigest()


def _set_session_cookies(response: Response, access_token: str, refresh_token: str, *, remember_me: bool = False) -> None:
    secure = settings.auth_cookie_secure
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        ACCESS_COOKIE, access_token, max_age=ACCESS_SECONDS, httponly=True,
        secure=secure, samesite="lax", path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE, refresh_token, max_age=REFRESH_SECONDS if remember_me else None, httponly=True,
        secure=secure, samesite="lax", path=f"{settings.api_prefix}/auth",
    )


def _clear_session_cookies(response: Response) -> None:
    secure = settings.auth_cookie_secure
    response.delete_cookie(ACCESS_COOKIE, path="/", secure=secure, httponly=True, samesite="lax")
    response.delete_cookie(REFRESH_COOKIE, path=f"{settings.api_prefix}/auth", secure=secure, httponly=True, samesite="lax")


def _clear_mfa_pending_cookies(response: Response) -> None:
    secure = settings.auth_cookie_secure
    path = f"{settings.api_prefix}/auth/mfa"
    response.delete_cookie(MFA_PENDING_COOKIE, path=path, secure=secure, httponly=True, samesite="strict")
    response.delete_cookie("mdis_mfa_remember", path=path, secure=secure, httponly=True, samesite="strict")


async def _new_session(
    db: AsyncSession,
    user: User,
    family_id: uuid.UUID | None = None,
    *,
    remember_me: bool = False,
) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    family_id = family_id or uuid.uuid4()
    refresh = secrets.token_urlsafe(48)
    token_row = RefreshToken(
        user_id=user.id,
        family_id=family_id,
        token_hash=_token_hash(refresh),
        expires_at=now + timedelta(seconds=REFRESH_SECONDS if remember_me else SESSION_SECONDS),
        remember_me=remember_me,
    )
    db.add(token_row)
    await db.flush()
    access = create_access_token({"sub": str(user.id), "sid": str(family_id)})
    return access, refresh


@router.get("/csrf")
async def get_csrf_cookie(response: Response) -> dict[str, bool]:
    """Bootstrap the double-submit CSRF cookie before login or unsafe requests."""
    response.set_cookie(
        CSRF_COOKIE,
        secrets.token_urlsafe(32),
        max_age=REFRESH_SECONDS,
        httponly=False,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"ready": True}


@router.get("/config")
async def auth_config(db: AsyncSession = Depends(get_db)) -> dict[str, object]:
    """Expose public signup options without user, credential, or clinical data."""
    organizations = (await db.execute(select(Organization.id, Organization.name).order_by(Organization.name))).all()
    return {
        "registration_mode": settings.registration_mode,
        "self_registration_enabled": settings.registration_mode == "approval",
        "organizations": [{"id": str(row.id), "name": row.name} for row in organizations],
    }


@router.post("/login", response_model=LoginResponse, dependencies=[Depends(csrf_protect)])
async def login(payload: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> LoginResponse:
    email = str(payload.email).strip().lower()
    await enforce_auth_rate_limit(request, db, "login", email)
    db.info["allow_unscoped_user_lookup"] = True
    try:
        result = await db.execute(select(User).where(User.email == email).with_for_update())
    finally:
        db.info.pop("allow_unscoped_user_lookup", None)
    user = result.scalars().first()
    now = datetime.now(timezone.utc)
    # Unknown accounts still pay the Argon2 verification cost, avoiding a fast
    # response that would reveal whether an email address exists.
    password_hash = user.password_hash if user and user.password_hash else DUMMY_PASSWORD_HASH
    password_ok = verify_password(payload.password, password_hash)
    status_only = user is not None and not user.is_active and user.registration_status in {
        RegistrationStatus.PENDING_EMAIL_VERIFICATION.value,
        RegistrationStatus.PENDING_APPROVAL.value,
        RegistrationStatus.REJECTED.value,
    }
    if user is None or (not user.is_active and not status_only) or (user.locked_until and user.locked_until > now) or not password_ok:
        if user is not None and user.is_active:
            currently_locked = bool(user.locked_until and user.locked_until > now)
            if not currently_locked:
                user.failed_login_count = (user.failed_login_count or 0) + 1
            if user.role != UserRole.ADMIN and not currently_locked and user.failed_login_count >= settings.auth_lockout_attempts:
                exponent = (user.failed_login_count - settings.auth_lockout_attempts) // settings.auth_lockout_attempts
                duration = min(settings.auth_lockout_minutes * (2 ** exponent), settings.auth_lockout_max_minutes)
                user.locked_until = now + timedelta(minutes=duration)
        await record_audit_event(
            db,
            action="LOGIN_FAILURE",
            user_id=user.id if user else None,
            organization_id=user.organization_id if user else None,
            request=request,
        )
        if user is not None and user.role == UserRole.ADMIN:
            await record_audit_event(db, action="ADMIN_LOGIN_FAILURE_ALERT", user_id=user.id, organization_id=user.organization_id, request=request)
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")

    if status_only:
        await record_audit_event(
            db,
            action="LOGIN_REGISTRATION_STATUS",
            user_id=user.id,
            organization_id=user.organization_id,
            request=request,
        )
        await db.commit()
        _clear_session_cookies(response)
        response.headers["Cache-Control"] = "no-store"
        status_messages = {
            RegistrationStatus.PENDING_EMAIL_VERIFICATION.value: "Verify your email address to continue.",
            RegistrationStatus.PENDING_APPROVAL.value: "Your account is awaiting organization approval.",
            RegistrationStatus.REJECTED.value: "Your account request was not approved.",
        }
        return LoginResponse(
            status=RegistrationStatus(user.registration_status),
            message=status_messages[user.registration_status],
            rejection_reason=user.rejection_reason if user.registration_status == RegistrationStatus.REJECTED.value else None,
        )

    if user.role in {UserRole.ADMIN, UserRole.OPERATOR} and (not user.mfa_enabled or not user.mfa_secret_encrypted):
        if password_needs_rehash(user.password_hash):
            user.password_hash = hash_password(payload.password)
            user.password_changed_at = now
        if payload.otp or payload.recovery_code:
            raise HTTPException(status_code=422, detail="Complete MFA enrollment before signing in")
        if not user.mfa_enabled or not user.mfa_secret_encrypted:
            raw_setup = await _issue_action_token(db, "mfa_setup", user.id, minutes=5)
            await record_audit_event(db, action="MFA_ENROLLMENT_REQUIRED", user_id=user.id, organization_id=user.organization_id, request=request)
            await db.commit()
            setup_response = JSONResponse(status_code=403, content={"detail": "MFA enrollment required"})
            setup_response.set_cookie("mdis_mfa_setup", raw_setup, max_age=300, httponly=True, secure=settings.auth_cookie_secure, samesite="strict", path=f"{settings.api_prefix}/auth/mfa")
            setup_response.set_cookie("mdis_mfa_remember", "1" if payload.remember_me else "0", max_age=300, httponly=True, secure=settings.auth_cookie_secure, samesite="strict", path=f"{settings.api_prefix}/auth/mfa")
            return setup_response

    if user.mfa_enabled:
        if payload.otp or payload.recovery_code:
            raise HTTPException(status_code=422, detail="Complete MFA verification separately")
        if not user.mfa_secret_encrypted:
            raise HTTPException(status_code=403, detail="MFA configuration is unavailable")
        if password_needs_rehash(user.password_hash):
            user.password_hash = hash_password(payload.password)
            user.password_changed_at = now
        raw_challenge = await _issue_action_token(db, "mfa_login", user.id, minutes=5)
        await record_audit_event(db, action="MFA_CHALLENGE_ISSUED", user_id=user.id, organization_id=user.organization_id, request=request)
        await db.commit()
        _clear_session_cookies(response)
        response.headers["Cache-Control"] = "no-store"
        path = f"{settings.api_prefix}/auth/mfa"
        response.set_cookie(MFA_PENDING_COOKIE, raw_challenge, max_age=300, httponly=True, secure=settings.auth_cookie_secure, samesite="strict", path=path)
        response.set_cookie("mdis_mfa_remember", "1" if payload.remember_me else "0", max_age=300, httponly=True, secure=settings.auth_cookie_secure, samesite="strict", path=path)
        return LoginResponse(status="pending_mfa", message="Additional verification is required.", mfa_required=True)

    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
        user.password_changed_at = now
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    family_id = uuid.uuid4()
    access_token, refresh_token = await _new_session(db, user, family_id, remember_me=payload.remember_me)
    _set_session_cookies(response, access_token, refresh_token, remember_me=payload.remember_me)
    await record_audit_event(db, action="LOGIN_SUCCESS", user_id=user.id, organization_id=user.organization_id, request=request)
    await db.commit()
    return LoginResponse(user=UserResponse.model_validate(user))


@router.post("/refresh", response_model=LoginResponse, dependencies=[Depends(csrf_protect)])
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> LoginResponse:
    raw_token = request.cookies.get(REFRESH_COOKIE)
    await enforce_auth_rate_limit(request, db, "refresh", _token_hash(raw_token) if raw_token else None)
    if not raw_token:
        raise unauthorized("Session expired")
    db.info["allow_unscoped_refresh_lookup"] = True
    try:
        row = await db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == _token_hash(raw_token)).with_for_update()
        )
    finally:
        db.info.pop("allow_unscoped_refresh_lookup", None)
    now = datetime.now(timezone.utc)
    if row is None:
        raise unauthorized("Session expired")
    if row.revoked_at is not None:
        await db.execute(
            update(RefreshToken).where(RefreshToken.family_id == row.family_id, RefreshToken.revoked_at.is_(None)).values(revoked_at=now)
        )
        db.info["allow_unscoped_user_lookup"] = True
        try:
            reuse_user = await db.get(User, row.user_id)
        finally:
            db.info.pop("allow_unscoped_user_lookup", None)
        await record_audit_event(db, action="TOKEN_REUSE_DETECTED", user_id=row.user_id, organization_id=reuse_user.organization_id if reuse_user else None, request=request)
        await db.commit()
        _clear_session_cookies(response)
        raise unauthorized("Session expired")
    if row.expires_at <= now:
        row.revoked_at = now
        await db.commit()
        _clear_session_cookies(response)
        raise unauthorized("Session expired")

    db.info["allow_unscoped_user_lookup"] = True
    try:
        user = await db.get(User, row.user_id)
    finally:
        db.info.pop("allow_unscoped_user_lookup", None)
    if user is None or not user.is_active or user.organization_id is None:
        row.revoked_at = now
        await db.commit()
        _clear_session_cookies(response)
        raise unauthorized("Session expired")
    db.info["organization_id"] = user.organization_id
    row.revoked_at = now
    new_access, new_refresh = await _new_session(db, user, row.family_id, remember_me=row.remember_me)
    replacement = await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == _token_hash(new_refresh)))
    row.replaced_by_id = replacement.id if replacement else None
    _set_session_cookies(response, new_access, new_refresh, remember_me=row.remember_me)
    await db.commit()
    return LoginResponse(user=UserResponse.model_validate(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(csrf_protect)])
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> Response:
    raw_token = request.cookies.get(REFRESH_COOKIE)
    if raw_token:
        db.info["allow_unscoped_refresh_lookup"] = True
        try:
            row = await db.scalar(
                select(RefreshToken).where(RefreshToken.token_hash == _token_hash(raw_token)).with_for_update()
            )
        finally:
            db.info.pop("allow_unscoped_refresh_lookup", None)
        if row is not None:
            now = datetime.now(timezone.utc)
            await db.execute(
                update(RefreshToken).where(RefreshToken.family_id == row.family_id, RefreshToken.revoked_at.is_(None)).values(revoked_at=now)
            )
            db.info["allow_unscoped_user_lookup"] = True
            try:
                logout_user = await db.get(User, row.user_id)
            finally:
                db.info.pop("allow_unscoped_user_lookup", None)
            await record_audit_event(db, action="LOGOUT", user_id=row.user_id, organization_id=logout_user.organization_id if logout_user else None, request=request)
            await db.commit()
    _clear_session_cookies(response)
    response.delete_cookie(CSRF_COOKIE, path="/", secure=settings.auth_cookie_secure, httponly=False, samesite="lax")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


async def _send_password_changed_safely(email: str, display_name: str) -> None:
    try:
        await send_password_changed_notice(email, display_name)
    except Exception:
        # Do not log addresses, action links, or provider response bodies.
        return


async def _send_account_notice_safely(email: str, template: EmailTemplate, display_name: str = "") -> None:
    try:
        await send_account_notice(email, template, display_name)
    except Exception:
        # Provider failures may include message data; keep them out of logs.
        return


@router.post("/forgot-password", dependencies=[Depends(csrf_protect)])
async def forgot_password(payload: ForgotPasswordRequest, request: Request, background: BackgroundTasks, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    await enforce_auth_rate_limit(request, db, "forgot_password", payload.email)
    await request_verification_code(db, request, background, payload.email, VerificationCodePurpose.RESET_PASSWORD)
    return {"message": "If the account exists, an email has been sent"}


@router.post("/codes/request", dependencies=[Depends(csrf_protect)])
async def request_email_code(
    payload: VerificationCodeRequest,
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    await request_verification_code(
        db,
        request,
        background,
        payload.email,
        VerificationCodePurpose(payload.purpose),
    )
    return {"message": "If the account exists, we sent a code"}


@router.post("/verify-reset-code", dependencies=[Depends(csrf_protect)])
async def verify_reset_code(
    payload: VerifyResetCodeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    valid = await verify_verification_code(db, request, payload.email, VerificationCodePurpose.RESET_PASSWORD, payload.code)
    if not valid:
        raise HTTPException(status_code=400, detail="Reset code is invalid or expired")
    db.info["allow_unscoped_user_lookup"] = True
    try:
        user = await db.scalar(select(User).where(User.email == payload.email))
    finally:
        db.info.pop("allow_unscoped_user_lookup", None)
    if user is None or not user.is_active:
        raise HTTPException(status_code=400, detail="Reset code is invalid or expired")
    grant = await _issue_action_token(db, "password_reset_grant", user.id, minutes=15)
    await record_audit_event(db, action="PASSWORD_RESET_GRANT_ISSUED", user_id=user.id, organization_id=user.organization_id, resource_type="password_reset_grant", request=request)
    await db.commit()
    return {"grant": grant, "expires_in": 900}


@router.post("/reset-password", dependencies=[Depends(csrf_protect)])
async def reset_password(payload: ResetPasswordRequest, request: Request, response: Response, background: BackgroundTasks, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    await enforce_auth_rate_limit(request, db, "reset_password", _token_hash(payload.grant))
    token = await _find_action_token(db, "password_reset_grant", payload.grant)
    if token is None or token.user_id is None:
        raise HTTPException(status_code=400, detail="Password reset grant is invalid or expired")
    db.info["allow_unscoped_user_lookup"] = True
    try:
        user = await db.get(User, token.user_id)
    finally:
        db.info.pop("allow_unscoped_user_lookup", None)
    if user is None or not user.is_active:
        raise HTTPException(status_code=400, detail="Password reset grant is invalid or expired")
    try:
        validate_password_policy(payload.new_password, email=user.email, full_name=user.full_name or "")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    now = datetime.now(timezone.utc)
    token.used_at = now
    user.password_hash = hash_password(payload.new_password)
    user.password_changed_at = now
    user.failed_login_count = 0
    user.locked_until = None
    await db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)).values(revoked_at=now))
    await db.execute(update(AuthActionToken).where(
        AuthActionToken.user_id == user.id,
        AuthActionToken.purpose.in_(("password_reset_grant", "mfa_login", "mfa_setup")),
        AuthActionToken.used_at.is_(None),
    ).values(used_at=now))
    await db.execute(update(AuthVerificationCode).where(
        AuthVerificationCode.user_id == user.id,
        AuthVerificationCode.purpose == VerificationCodePurpose.RESET_PASSWORD.value,
        AuthVerificationCode.is_used.is_(False),
        AuthVerificationCode.invalidated_at.is_(None),
    ).values(invalidated_at=now))
    await record_audit_event(db, action="PASSWORD_RESET_COMPLETED", user_id=user.id, organization_id=user.organization_id, request=request)
    await record_audit_event(db, action="PASSWORD_CHANGED", user_id=user.id, organization_id=user.organization_id, request=request)
    await db.commit()
    background.add_task(_send_password_changed_safely, user.email, user.full_name or "")
    _clear_session_cookies(response)
    response.delete_cookie(CSRF_COOKIE, path="/", secure=settings.auth_cookie_secure, httponly=False, samesite="lax")
    response.headers["Cache-Control"] = "no-store"
    return {"message": "Password has been reset. Sign in again."}


@router.post("/change-password", dependencies=[Depends(csrf_protect), Depends(require_roles(*tuple(UserRole)))])
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    background: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Change the authenticated user's password and immediately revoke sessions."""
    await enforce_auth_rate_limit(request, db, "change_password", str(current_user.id))
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    try:
        validate_password_policy(payload.new_password, email=current_user.email, full_name=current_user.full_name or "")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    now = datetime.now(timezone.utc)
    current_user.password_hash = hash_password(payload.new_password)
    current_user.password_changed_at = now
    await db.execute(update(RefreshToken).where(RefreshToken.user_id == current_user.id, RefreshToken.revoked_at.is_(None)).values(revoked_at=now))
    await record_audit_event(db, action="PASSWORD_CHANGED", user_id=current_user.id, organization_id=current_user.organization_id, request=request)
    await db.commit()
    background.add_task(_send_password_changed_safely, current_user.email, current_user.full_name or "")
    _clear_session_cookies(response)
    response.delete_cookie(CSRF_COOKIE, path="/", secure=settings.auth_cookie_secure, httponly=False, samesite="lax")
    response.headers["Cache-Control"] = "no-store"
    return {"message": "Password changed. Sign in again."}


@router.post("/register", status_code=202, dependencies=[Depends(csrf_protect)])
async def self_register(payload: RegistrationRequest, request: Request, background: BackgroundTasks, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    started = time.monotonic()
    if settings.registration_mode == "disabled":
        raise HTTPException(status_code=404, detail="Not found")
    if settings.registration_mode == "invite_only":
        raise HTTPException(status_code=404, detail="Not found")
    if not email_delivery_available():
        raise HTTPException(status_code=503, detail="Email delivery is not configured")
    await enforce_auth_rate_limit(request, db, "register", payload.work_email)
    if payload.organization_id is not None:
        organization = await db.scalar(select(Organization.id).where(Organization.id == payload.organization_id))
        if organization is None:
            raise HTTPException(status_code=422, detail="Select an available organization")
        organization_id = payload.organization_id
        requested_organization_name = None
    else:
        # Requests for an organization not present in the public directory enter the
        # default organization's review queue; the name is not used as a tenant ID.
        organization_id = DEFAULT_ORGANIZATION_ID
        requested_organization_name = payload.organization_request_name
    db.info["allow_unscoped_user_lookup"] = True
    try:
        existing = await db.scalar(select(User).where(User.email == payload.work_email))
    finally:
        db.info.pop("allow_unscoped_user_lookup", None)
    if existing:
        # Match the password-hashing work on new-account creation so duplicate
        # emails do not get a cheap timing signal.
        verify_password(payload.password, DUMMY_PASSWORD_HASH)
        background.add_task(_send_account_notice_safely, existing.email, EmailTemplate.ACCOUNT_EXISTS, existing.full_name or "")
        remaining = settings.auth_enumeration_min_response_ms / 1000 - (time.monotonic() - started)
        if remaining > 0:
            await asyncio.sleep(remaining)
        return {"message": "If registration is accepted, an account is pending approval."}
    try:
        validate_password_policy(payload.password, email=payload.work_email, full_name=payload.full_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    user = User(
        email=payload.work_email,
        display_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        role=UserRole.VIEWER,
        organization_id=organization_id,
        is_active=False,
        pending_approval=True,
        email_verified=False,
        registration_status=RegistrationStatus.PENDING_EMAIL_VERIFICATION.value,
        professional_role_requested=payload.professional_role,
        license_or_certification_number=payload.license_or_certification_number,
        license_type=payload.license_type,
        requested_organization_name=requested_organization_name,
        phone=payload.phone,
        terms_accepted_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    await record_audit_event(db, action="ACCOUNT_CREATED", user_id=user.id, organization_id=user.organization_id, request=request)
    await db.commit()
    await request_verification_code(db, request, background, payload.work_email, VerificationCodePurpose.VERIFY_EMAIL)
    return {"message": "If registration is accepted, an account is pending approval."}


class ResendVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


@router.post("/resend-verification", dependencies=[Depends(csrf_protect)])
async def resend_verification(payload: ResendVerificationRequest, request: Request, background: BackgroundTasks, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    await request_verification_code(db, request, background, payload.email, VerificationCodePurpose.VERIFY_EMAIL)
    return {"message": "If the account exists, we sent a code."}


@router.post("/verify-email", dependencies=[Depends(csrf_protect)])
async def verify_email(payload: VerifyEmailRequest, request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    valid = await verify_verification_code(db, request, payload.email, VerificationCodePurpose.VERIFY_EMAIL, payload.code)
    if not valid:
        raise HTTPException(status_code=400, detail="Verification code is invalid or expired")
    db.info["allow_unscoped_user_lookup"] = True
    try:
        user = await db.scalar(select(User).where(User.email == payload.email).with_for_update())
    finally:
        db.info.pop("allow_unscoped_user_lookup", None)
    if user is None or user.registration_status != RegistrationStatus.PENDING_EMAIL_VERIFICATION.value:
        raise HTTPException(status_code=400, detail="Verification code is invalid or expired")
    user.email_verified = True
    user.registration_status = RegistrationStatus.PENDING_APPROVAL.value
    user.pending_approval = True
    await record_audit_event(db, action="EMAIL_VERIFIED", user_id=user.id, organization_id=user.organization_id, request=request)
    await db.commit()
    return {"status": RegistrationStatus.PENDING_APPROVAL.value, "message": "Email verified. Your account is awaiting organization approval."}


@router.post("/mfa/enroll", dependencies=[Depends(csrf_protect), Depends(require_roles(*tuple(UserRole)))])
async def start_mfa_enrollment(request: Request, response: Response, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict[str, bool]:
    raw = await _issue_action_token(db, "mfa_setup", current_user.id, minutes=5)
    response.set_cookie("mdis_mfa_setup", raw, max_age=300, httponly=True, secure=settings.auth_cookie_secure, samesite="strict", path=f"{settings.api_prefix}/auth/mfa")
    await db.commit()
    return {"setup_required": True}


@router.post("/mfa/setup", dependencies=[Depends(csrf_protect)])
async def setup_mfa(request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    await enforce_auth_rate_limit(request, db, "mfa_setup", request.cookies.get("mdis_mfa_setup"))
    raw = request.cookies.get("mdis_mfa_setup")
    token = await _find_action_token(db, "mfa_setup", raw) if raw else None
    if token is None or token.user_id is None:
        raise HTTPException(status_code=401, detail="MFA setup session expired")
    db.info["allow_unscoped_user_lookup"] = True
    try:
        user = await db.get(User, token.user_id)
    finally:
        db.info.pop("allow_unscoped_user_lookup", None)
    if user is None:
        raise HTTPException(status_code=401, detail="MFA setup session expired")
    try:
        secret = new_totp_secret()
        user.mfa_secret_encrypted = encrypt_secret(secret)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="MFA encryption is not configured") from exc
    await db.commit()
    return {"provisioning_uri": provisioning_uri(secret, user.email)}


@router.post("/mfa/enable", dependencies=[Depends(csrf_protect)])
async def enable_mfa(payload: MFARequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> dict[str, object]:
    raw = request.cookies.get("mdis_mfa_setup")
    await enforce_auth_rate_limit(request, db, "mfa_verify", raw)
    token = await _find_action_token(db, "mfa_setup", raw) if raw else None
    if token is None or token.user_id is None:
        raise HTTPException(status_code=401, detail="MFA setup session expired")
    db.info["allow_unscoped_user_lookup"] = True
    try:
        user = await db.get(User, token.user_id)
    finally:
        db.info.pop("allow_unscoped_user_lookup", None)
    if user is None or not user.mfa_secret_encrypted or not verify_totp(decrypt_secret(user.mfa_secret_encrypted), payload.code):
        await record_audit_event(db, action="MFA_VERIFY_FAILURE", user_id=token.user_id, organization_id=user.organization_id if user else None, request=request)
        await db.commit()
        raise HTTPException(status_code=401, detail="MFA code is invalid")
    now = datetime.now(timezone.utc)
    recovery_codes = new_recovery_codes()
    user.mfa_enabled = True
    user.recovery_code_hashes = [recovery_hash(code) for code in recovery_codes]
    token.used_at = now
    # Do not let a pre-MFA refresh family become privileged once the flag flips on.
    await db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)).values(revoked_at=now))
    remember_me = request.cookies.get("mdis_mfa_remember") == "1"
    access, refresh_token = await _new_session(db, user, remember_me=remember_me)
    _set_session_cookies(response, access, refresh_token, remember_me=remember_me)
    response.delete_cookie("mdis_mfa_setup", path=f"{settings.api_prefix}/auth/mfa", secure=settings.auth_cookie_secure, httponly=True, samesite="strict")
    response.delete_cookie("mdis_mfa_remember", path=f"{settings.api_prefix}/auth/mfa", secure=settings.auth_cookie_secure, httponly=True, samesite="strict")
    await record_audit_event(db, action="MFA_ENABLED", user_id=user.id, organization_id=user.organization_id, request=request)
    await db.commit()
    return {"enabled": True, "recovery_codes": recovery_codes}


@router.post("/mfa/verify-login", dependencies=[Depends(csrf_protect)])
async def verify_mfa_login(
    payload: MFARequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Complete a password login challenge without accepting MFA on the first step."""
    raw_challenge = request.cookies.get(MFA_PENDING_COOKIE)
    if not raw_challenge:
        raise unauthorized("MFA verification session expired")
    await enforce_auth_rate_limit(request, db, "mfa_login_challenge_ip", mfa=True)
    challenge = await _find_action_token(db, "mfa_login", raw_challenge)
    if challenge is None or challenge.user_id is None:
        _clear_mfa_pending_cookies(response)
        raise unauthorized("MFA verification session expired")

    db.info["allow_unscoped_user_lookup"] = True
    try:
        user = await db.get(User, challenge.user_id)
    finally:
        db.info.pop("allow_unscoped_user_lookup", None)
    if (
        user is None
        or not user.is_active
        or not user.mfa_enabled
        or not user.mfa_secret_encrypted
    ):
        raise unauthorized("MFA verification session expired")

    await enforce_auth_rate_limit(request, db, "mfa_login_account", str(user.id), mfa=True)
    valid = False
    try:
        if len(payload.code) == 6 and payload.code.isdigit():
            valid = verify_totp(decrypt_secret(user.mfa_secret_encrypted), payload.code)
        if not valid and user.recovery_code_hashes:
            recovery_code_hash = recovery_hash(payload.code)
            if recovery_code_hash in user.recovery_code_hashes:
                user.recovery_code_hashes = [value for value in user.recovery_code_hashes if value != recovery_code_hash]
                valid = True
    except Exception:
        valid = False
    if not valid:
        await record_audit_event(db, action="MFA_VERIFY_FAILURE", user_id=user.id, organization_id=user.organization_id, request=request)
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="MFA verification failed")

    now = datetime.now(timezone.utc)
    challenge.used_at = now
    await db.execute(update(AuthActionToken).where(
        AuthActionToken.user_id == user.id,
        AuthActionToken.purpose == "mfa_login",
        AuthActionToken.used_at.is_(None),
    ).values(used_at=now))
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    remember_me = request.cookies.get("mdis_mfa_remember") == "1"
    access_token, refresh_token = await _new_session(db, user, remember_me=remember_me)
    _set_session_cookies(response, access_token, refresh_token, remember_me=remember_me)
    _clear_mfa_pending_cookies(response)
    await record_audit_event(db, action="MFA_VERIFY_SUCCESS", user_id=user.id, organization_id=user.organization_id, request=request)
    await record_audit_event(db, action="LOGIN_SUCCESS", user_id=user.id, organization_id=user.organization_id, request=request)
    await db.commit()
    return LoginResponse(user=UserResponse.model_validate(user))


@router.post("/mfa/disable", dependencies=[Depends(csrf_protect), Depends(require_roles(*tuple(UserRole)))])
async def disable_mfa(payload: LoginRequest, request: Request, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict[str, bool]:
    await enforce_auth_rate_limit(request, db, "mfa_verify", str(current_user.id), mfa=True)
    if current_user.role in {UserRole.ADMIN, UserRole.OPERATOR}:
        raise HTTPException(status_code=403, detail="MFA is required for this role")
    if payload.email.casefold() != current_user.email.casefold() or not verify_password(payload.password, current_user.password_hash):
        raise HTTPException(status_code=401, detail="Authentication failed")
    if not current_user.mfa_enabled or not current_user.mfa_secret_encrypted or not verify_totp(decrypt_secret(current_user.mfa_secret_encrypted), payload.otp or ""):
        raise HTTPException(status_code=401, detail="MFA code is invalid")
    current_user.mfa_enabled = False
    current_user.mfa_secret_encrypted = None
    current_user.recovery_code_hashes = None
    await record_audit_event(db, action="MFA_DISABLED", user_id=current_user.id, organization_id=current_user.organization_id, request=request)
    await db.commit()
    return {"enabled": False}


@router.get("/me", response_model=UserResponse)
async def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user
