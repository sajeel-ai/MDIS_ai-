"""Role-Based Access Control (RBAC)."""

from typing import Sequence
from fastapi import HTTPException, status, Depends
from app.models import User, UserRole
from app.security.auth import get_current_user


class RoleChecker:
    def __init__(self, allowed_roles: Sequence[UserRole]):
        self.allowed_roles = allowed_roles

    def __call__(self, user: User = Depends(get_current_user)):
        if user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User role '{user.role}' lacks permission for this endpoint",
            )
        return user
