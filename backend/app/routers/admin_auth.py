"""Organization-scoped invitation and account/session administration APIs."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.dependencies.auth import UserContext, UserRole
from app.dependencies.permissions import require_roles
from app.models import AuthActionToken, RefreshToken, RegistrationStatus, User
from app.routers.auth import _issue_action_token, _token_hash, csrf_protect
from app.security.auth import hash_password, validate_password_policy
from app.services.audit_service import record_audit_event
from app.services.auth_rate_limit import enforce_auth_rate_limit
from app.services.email_provider import action_link, configured_email_provider, send_action_link, send_account_notice
from app.services.email_templates import EmailTemplate


router = APIRouter(prefix="/admin", tags=["account administration"])
admin_only = Depends(require_roles(UserRole.ADMIN))


class InviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=256)
    full_name: str = Field(min_length=1, max_length=128)
    role: UserRole
    confirm_privileged: bool = False

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or any(character.isspace() for character in normalized):
            raise ValueError("Invalid email")
        return normalized


class AcceptInviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=20, max_length=256)
    password: str = Field(min_length=12, max_length=1024)


class RoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: UserRole
    confirm_privileged: bool = False
    expected_updated_at: datetime | None = None


class AccountRequestApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: UserRole
    confirm_privileged: bool = False
    expected_updated_at: datetime | None = None


class AccountRequestRejection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def trim_reason(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("A rejection reason is required")
        return cleaned


async def _send_account_notice_safely(email: str, template: EmailTemplate, display_name: str) -> None:
    try:
        await send_account_notice(email, template, display_name)
    except Exception:
        # Provider errors may contain recipient or message content; do not log them.
        return


async def _send_invite_safely(email: str, token: str) -> None:
    try:
        await send_action_link(email, "invite-accept", token)
    except Exception:
        # Provider errors can include recipient or message data; do not log them.
        return


@router.post("/invitations", status_code=201, dependencies=[admin_only])
async def create_invitation(
    payload: InviteRequest,
    request: Request,
    background: BackgroundTasks,
    current_user: UserContext = Depends(require_roles(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    email = str(payload.email).strip().lower()
    if payload.role in {UserRole.ADMIN, UserRole.OPERATOR} and not payload.confirm_privileged:
        await _audit_denial_and_raise(db, current_user, request, "Explicit confirmation is required when assigning an administrator or operator role")
    existing = await db.scalar(select(User.id).where(User.email == email))
    if existing:
        raise HTTPException(status_code=409, detail="Account already exists")
    invited = User(
        email=email,
        display_name=payload.full_name.strip(),
        role=payload.role,
        organization_id=current_user.organization_id,
        is_active=False,
        pending_approval=False,
    )
    db.add(invited)
    await db.flush()
    raw = await _issue_action_token(db, "invite_accept", invited.id, minutes=60 * 24)
    link = action_link("invite-accept", raw)
    provider_ready = configured_email_provider() is not None
    delivery = "not_configured"
    if link and provider_ready:
        background.add_task(_send_invite_safely, email, raw)
        delivery = "queued"
    await record_audit_event(db, action="ACCOUNT_INVITED", user_id=current_user.id, organization_id=current_user.organization_id, resource_type="user", resource_id=invited.id, request=request)
    await db.commit()
    warning = "target_user_mfa_not_enrolled" if payload.role in {UserRole.ADMIN, UserRole.OPERATOR} else ""
    return {"status": "invited", "email_delivery": delivery, "warning": warning}


@router.post("/invitations/accept", dependencies=[Depends(csrf_protect)])
async def accept_invitation(payload: AcceptInviteRequest, request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    await enforce_auth_rate_limit(request, db, "invite_accept", _token_hash(payload.token))
    token = await db.scalar(select(AuthActionToken).where(
        AuthActionToken.purpose == "invite_accept",
        AuthActionToken.token_hash == _token_hash(payload.token),
        AuthActionToken.used_at.is_(None),
        AuthActionToken.expires_at > datetime.now(timezone.utc),
    ).with_for_update())
    if token is None or token.user_id is None:
        raise HTTPException(status_code=400, detail="Invitation link is invalid or expired")
    db.info["allow_unscoped_user_lookup"] = True
    try:
        invited = await db.get(User, token.user_id)
    finally:
        db.info.pop("allow_unscoped_user_lookup", None)
    if invited is None or invited.is_active:
        raise HTTPException(status_code=400, detail="Invitation link is invalid or expired")
    try:
        validate_password_policy(payload.password, email=invited.email, full_name=invited.full_name or "")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    invited.password_hash = hash_password(payload.password)
    invited.password_changed_at = datetime.now(timezone.utc)
    invited.is_active = True
    invited.pending_approval = False
    invited.email_verified = True
    invited.registration_status = RegistrationStatus.APPROVED.value
    token.used_at = datetime.now(timezone.utc)
    await record_audit_event(db, action="ACCOUNT_CREATED", user_id=invited.id, organization_id=invited.organization_id, request=request)
    await db.commit()
    return {"status": "accepted", "message": "Invitation accepted. Sign in to continue."}


@router.get("/users", dependencies=[admin_only])
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    q: str | None = Query(None, max_length=256),
    role: UserRole | None = Query(None),
    status: str | None = Query(None, pattern="^(active|inactive)$"),
    mfa: str | None = Query(None, pattern="^(enabled|disabled)$"),
    current_user: UserContext = Depends(require_roles(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    filters = [User.organization_id == current_user.organization_id]
    if q and q.strip():
        term = f"%{q.strip().lower()}%"
        filters.append(func.lower(User.email).like(term) | func.lower(User.display_name).like(term))
    if role is not None:
        filters.append(User.role == role)
    if status == "active":
        filters.append(User.is_active.is_(True))
    elif status == "inactive":
        filters.append(User.is_active.is_(False))
    if mfa == "enabled":
        filters.append(User.mfa_enabled.is_(True))
    elif mfa == "disabled":
        filters.append(User.mfa_enabled.is_(False))
    total = int(await db.scalar(select(func.count()).select_from(User).where(*filters)) or 0)
    offset = (page - 1) * page_size
    users = (await db.scalars(select(User).where(*filters).order_by(User.created_at.desc(), User.id.desc()).offset(offset).limit(page_size))).all()
    ids = [user.id for user in users]
    session_counts: dict[uuid.UUID, int] = {}
    if ids:
        rows = await db.execute(select(RefreshToken.user_id, func.count(RefreshToken.id)).where(
            RefreshToken.user_id.in_(ids),
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > datetime.now(timezone.utc),
        ).group_by(RefreshToken.user_id))
        session_counts = {user_id: int(count) for user_id, count in rows.all()}
    items = [{"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role.value, "is_active": user.is_active, "pending_approval": user.pending_approval, "mfa_enabled": user.mfa_enabled, "session_count": session_counts.get(user.id, 0), "updated_at": user.updated_at} for user in users]
    return {"items": items, "total": total, "page": page, "page_size": page_size, "has_next": offset + len(items) < total}


@router.get("/account-requests", dependencies=[admin_only])
async def list_account_requests(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    q: str | None = Query(None, max_length=256),
    current_user: UserContext = Depends(require_roles(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """List verified registration requests inside the administrator's organization."""
    filters = [
            User.organization_id == current_user.organization_id,
            User.registration_status == RegistrationStatus.PENDING_APPROVAL.value,
            User.email_verified.is_(True),
    ]
    if q and q.strip():
        term = f"%{q.strip().lower()}%"
        filters.append(func.lower(User.email).like(term) | func.lower(User.display_name).like(term))
    total = int(await db.scalar(select(func.count()).select_from(User).where(*filters)) or 0)
    offset = (page - 1) * page_size
    users = (await db.scalars(select(User).where(*filters).order_by(User.created_at.asc(), User.id.asc()).offset(offset).limit(page_size))).all()
    items = [
        {
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "professional_role_requested": user.professional_role_requested,
            "license_or_certification_number": user.license_or_certification_number,
            "license_type": user.license_type,
            "requested_organization_name": user.requested_organization_name,
            "created_at": user.created_at,
        }
        for user in users
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size, "has_next": offset + len(items) < total}


async def _pending_account_request(db: AsyncSession, current_user: UserContext, user_id: uuid.UUID) -> User:
    user = await db.scalar(select(User).where(
        User.id == user_id,
        User.organization_id == current_user.organization_id,
        User.registration_status == RegistrationStatus.PENDING_APPROVAL.value,
        User.email_verified.is_(True),
    ).with_for_update())
    if user is None:
        raise HTTPException(status_code=404, detail="Account request not found")
    return user


async def _audit_denial_and_raise(
    db: AsyncSession,
    current_user: UserContext,
    request: Request,
    detail: str,
    resource_id: uuid.UUID | None = None,
) -> None:
    await record_audit_event(
        db,
        action="AUTHZ_DENIED",
        user_id=current_user.id,
        organization_id=current_user.organization_id,
        resource_type="user",
        resource_id=resource_id,
        request=request,
    )
    await db.commit()
    raise HTTPException(status_code=409, detail=detail)


async def _lock_active_admins(db: AsyncSession, organization_id: uuid.UUID) -> list[User]:
    """Lock the organization's admin rows before checking the last-admin rule."""
    return list((await db.scalars(
        select(User)
        .where(
            User.organization_id == organization_id,
            User.role == UserRole.ADMIN,
            User.is_active.is_(True),
        )
        .with_for_update()
    )).all())


def _stale_record(expected: datetime | None, actual: datetime | None) -> bool:
    return expected is not None and actual is not None and expected != actual


@router.post("/account-requests/{user_id}/approve", dependencies=[admin_only])
async def approve_account_request(
    user_id: uuid.UUID,
    payload: AccountRequestApproval,
    request: Request,
    background: BackgroundTasks,
    current_user: UserContext = Depends(require_roles(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    user = await _pending_account_request(db, current_user, user_id)
    if payload.role in {UserRole.ADMIN, UserRole.OPERATOR} and not payload.confirm_privileged:
        await _audit_denial_and_raise(db, current_user, request, "Explicit confirmation is required when assigning an administrator or operator role", user.id)
    if _stale_record(payload.expected_updated_at, user.updated_at):
        await _audit_denial_and_raise(db, current_user, request, "This account changed; reload and try again", user.id)
    if user.requested_organization_name:
        raise HTTPException(status_code=409, detail="Requested organization must be verified before approval")
    user.role = payload.role
    user.is_active = True
    user.pending_approval = False
    user.registration_status = RegistrationStatus.APPROVED.value
    user.rejection_reason = None
    await record_audit_event(db, action="ACCOUNT_APPROVED", user_id=current_user.id, organization_id=current_user.organization_id, resource_type="user", resource_id=user.id, request=request)
    await db.commit()
    delivery = "queued" if configured_email_provider() is not None else "not_configured"
    if delivery == "queued":
        background.add_task(_send_account_notice_safely, user.email, EmailTemplate.ACCOUNT_APPROVED, user.full_name or "")
    warning = "target_user_mfa_not_enrolled" if payload.role in {UserRole.ADMIN, UserRole.OPERATOR} and not user.mfa_enabled else ""
    return {"status": "approved", "email_delivery": delivery, "warning": warning}


@router.post("/account-requests/{user_id}/reject", dependencies=[admin_only])
async def reject_account_request(
    user_id: uuid.UUID,
    payload: AccountRequestRejection,
    request: Request,
    background: BackgroundTasks,
    current_user: UserContext = Depends(require_roles(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    user = await _pending_account_request(db, current_user, user_id)
    user.is_active = False
    user.pending_approval = False
    user.registration_status = RegistrationStatus.REJECTED.value
    user.rejection_reason = payload.reason
    now = datetime.now(timezone.utc)
    await db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)).values(revoked_at=now))
    await record_audit_event(db, action="ACCOUNT_REJECTED", user_id=current_user.id, organization_id=current_user.organization_id, resource_type="user", resource_id=user.id, request=request)
    await db.commit()
    delivery = "queued" if configured_email_provider() is not None else "not_configured"
    if delivery == "queued":
        background.add_task(_send_account_notice_safely, user.email, EmailTemplate.ACCOUNT_REJECTED, user.full_name or "")
    return {"status": "rejected", "email_delivery": delivery}


async def _org_user(db: AsyncSession, current_user: UserContext, user_id: uuid.UUID) -> User:
    user = await db.scalar(select(User).where(User.id == user_id, User.organization_id == current_user.organization_id))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/users/{user_id}/role", dependencies=[admin_only])
async def change_role(user_id: uuid.UUID, payload: RoleUpdate, request: Request, current_user: UserContext = Depends(require_roles(UserRole.ADMIN)), db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    user = await _org_user(db, current_user, user_id)
    if user.id == current_user.id:
        await _audit_denial_and_raise(db, current_user, request, "Administrators cannot change their own role", user.id)
    if payload.role in {UserRole.ADMIN, UserRole.OPERATOR} and not payload.confirm_privileged:
        await _audit_denial_and_raise(db, current_user, request, "Explicit confirmation is required when assigning an administrator or operator role", user.id)
    if _stale_record(payload.expected_updated_at, user.updated_at):
        await _audit_denial_and_raise(db, current_user, request, "This account changed; reload and try again", user.id)
    if user.role == UserRole.ADMIN and user.is_active and payload.role != UserRole.ADMIN:
        admins = await _lock_active_admins(db, current_user.organization_id)
        await db.refresh(user)
        if len(admins) <= 1:
            await _audit_denial_and_raise(db, current_user, request, "The organization must retain at least one active administrator", user.id)
    old_role = user.role
    user.role = payload.role
    if payload.role in {UserRole.ADMIN, UserRole.OPERATOR} and not user.mfa_enabled:
        user.locked_until = None
    if payload.role in {UserRole.ADMIN, UserRole.OPERATOR} and old_role not in {UserRole.ADMIN, UserRole.OPERATOR}:
        await db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)).values(revoked_at=datetime.now(timezone.utc)))
        await record_audit_event(db, action="SESSION_REVOKED", user_id=current_user.id, organization_id=current_user.organization_id, resource_type="user_sessions", resource_id=user.id, request=request)
    await record_audit_event(db, action="ROLE_CHANGED", user_id=current_user.id, organization_id=current_user.organization_id, resource_type="user", resource_id=user.id, request=request)
    await db.commit()
    warning = "target_user_mfa_not_enrolled" if user.role in {UserRole.ADMIN, UserRole.OPERATOR} and not user.mfa_enabled else ""
    return {"status": "updated", "role": user.role.value, "warning": warning}


@router.post("/users/{user_id}/deactivate", dependencies=[admin_only])
async def deactivate_user(user_id: uuid.UUID, request: Request, expected_updated_at: datetime | None = None, current_user: UserContext = Depends(require_roles(UserRole.ADMIN)), db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    user = await _org_user(db, current_user, user_id)
    if user.id == current_user.id:
        await _audit_denial_and_raise(db, current_user, request, "Administrators cannot deactivate their own account", user.id)
    if _stale_record(expected_updated_at, user.updated_at):
        await _audit_denial_and_raise(db, current_user, request, "This account changed; reload and try again", user.id)
    if user.role == UserRole.ADMIN and user.is_active:
        admins = await _lock_active_admins(db, current_user.organization_id)
        await db.refresh(user)
        if len(admins) <= 1:
            await _audit_denial_and_raise(db, current_user, request, "The organization must retain at least one active administrator", user.id)
    user.is_active = False
    now = datetime.now(timezone.utc)
    await db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)).values(revoked_at=now))
    await record_audit_event(db, action="ACCOUNT_DISABLED", user_id=current_user.id, organization_id=current_user.organization_id, resource_type="user", resource_id=user.id, request=request)
    await record_audit_event(db, action="SESSION_REVOKED", user_id=current_user.id, organization_id=current_user.organization_id, resource_type="user_sessions", resource_id=user.id, request=request)
    await db.commit()
    return {"status": "deactivated"}


@router.post("/users/{user_id}/reactivate", dependencies=[admin_only])
async def reactivate_user(user_id: uuid.UUID, request: Request, current_user: UserContext = Depends(require_roles(UserRole.ADMIN)), db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    user = await _org_user(db, current_user, user_id)
    if user.pending_approval or user.registration_status in {
        RegistrationStatus.PENDING_EMAIL_VERIFICATION.value,
        RegistrationStatus.PENDING_APPROVAL.value,
    }:
        raise HTTPException(status_code=409, detail="Pending self-registration requires approval")
    user.is_active = True
    await record_audit_event(db, action="ACCOUNT_REACTIVATED", user_id=current_user.id, organization_id=current_user.organization_id, resource_type="user", resource_id=user.id, request=request)
    await db.commit()
    return {"status": "reactivated"}


@router.get("/users/{user_id}/sessions", dependencies=[admin_only])
async def list_sessions(user_id: uuid.UUID, current_user: UserContext = Depends(require_roles(UserRole.ADMIN)), db: AsyncSession = Depends(get_db)) -> list[dict[str, object]]:
    await _org_user(db, current_user, user_id)
    rows = (await db.scalars(select(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None), RefreshToken.expires_at > datetime.now(timezone.utc)).order_by(RefreshToken.created_at.desc()))).all()
    return [{"family_id": row.family_id, "created_at": row.created_at, "expires_at": row.expires_at} for row in rows]


@router.delete("/users/{user_id}/sessions/{family_id}", dependencies=[admin_only])
async def revoke_session(user_id: uuid.UUID, family_id: uuid.UUID, request: Request, current_user: UserContext = Depends(require_roles(UserRole.ADMIN)), db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    await _org_user(db, current_user, user_id)
    result = await db.execute(update(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None)).values(revoked_at=datetime.now(timezone.utc)))
    if not result.rowcount:
        raise HTTPException(status_code=404, detail="Session not found")
    await record_audit_event(db, action="SESSION_REVOKED", user_id=current_user.id, organization_id=current_user.organization_id, resource_type="session", resource_id=family_id, request=request)
    await db.commit()
    return {"status": "revoked"}
