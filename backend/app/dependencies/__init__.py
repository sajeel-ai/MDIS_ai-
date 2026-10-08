"""Cognate AI API Dependencies."""

from app.dependencies.auth import UserContext, UserRole, get_current_user
from app.dependencies.permissions import require_authenticated_user, require_org_access, require_role, require_roles
from app.dependencies.access import verify_patient_access, verify_document_access

__all__ = [
    "UserContext",
    "UserRole",
    "get_current_user",
    "require_roles",
    "require_role",
    "require_authenticated_user",
    "require_org_access",
    "verify_patient_access",
    "verify_document_access",
]
