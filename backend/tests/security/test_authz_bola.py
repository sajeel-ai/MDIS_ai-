"""Security Authorization & BOLA Unit Tests."""

import uuid
import pytest
from fastapi import HTTPException
from starlette.requests import Request
from app.models import User, UserRole
from app.security.rbac import RoleChecker
from app.models.organization import DEFAULT_ORGANIZATION_ID
from app.dependencies.permissions import require_org_access
from app.security.authorization import authorize_document_access


@pytest.mark.asyncio
async def test_role_checker_denies_unauthorized_role():
    clinician_user = User(email="clinician@example.test", role=UserRole.CLINICIAN)
    checker = RoleChecker(allowed_roles=[UserRole.ADMIN, UserRole.OPERATOR])

    with pytest.raises(HTTPException) as exc_info:
        checker(user=clinician_user)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_role_checker_allows_authorized_role():
    admin_user = User(email="admin@example.test", role=UserRole.ADMIN)
    checker = RoleChecker(allowed_roles=[UserRole.ADMIN])
    result = checker(user=admin_user)
    assert result.email == "admin@example.test"


@pytest.mark.asyncio
async def test_organization_dependency_hides_cross_organization_ids():
    user = User(email="clinician@example.test", role=UserRole.CLINICIAN, organization_id=DEFAULT_ORGANIZATION_ID)
    request = Request({
        "type": "http",
        "method": "GET",
        "path": "/organizations/00000000-0000-4000-8000-000000000000",
        "headers": [],
        "query_string": b"",
        "path_params": {"organization_id": "00000000-0000-4000-8000-000000000000"},
        "server": ("test", 80),
        "client": ("test", 1),
        "scheme": "http",
    })
    with pytest.raises(HTTPException) as exc_info:
        await require_org_access(request, user)
    assert exc_info.value.status_code == 404
