"""Role-based access control permission dependencies."""

from typing import Callable
import uuid

from fastapi import Depends, HTTPException, Request, status

from app.dependencies.auth import UserContext, UserRole, get_current_user
from app.db import get_db
from app.services.audit_service import record_audit_event
from sqlalchemy.ext.asyncio import AsyncSession


def require_roles(*allowed_roles: UserRole) -> Callable:
    """Dependency factory ensuring current user possesses at least one allowed role."""

    async def role_checker(
        request: Request,
        current_user: UserContext = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> UserContext:
        current_role = getattr(current_user.role, "value", current_user.role)
        if not any(role.value.lower() == str(current_role).lower() for role in allowed_roles):
            await record_audit_event(
                db,
                action="AUTHZ_DENIED",
                user_id=current_user.id,
                organization_id=current_user.organization_id,
                request=request,
            )
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User lacks required role: {[r.value for r in allowed_roles]}",
            )
        return current_user

    return role_checker


def require_role(*allowed_roles: UserRole) -> Callable:
    """Singular spelling for the existing role dependency API."""
    return require_roles(*allowed_roles)


require_authenticated_user = get_current_user


async def require_org_access(
    request: Request,
    current_user: UserContext = Depends(get_current_user),
) -> UserContext:
    """Require an explicit organization path parameter matching the session user."""
    try:
        requested_org_id = uuid.UUID(str(request.path_params.get("organization_id", "")))
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    if current_user.organization_id is None or requested_org_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return current_user
