"""Exercise the role dependencies attached to each protected API route."""

from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from types import SimpleNamespace

from app.main import app
from app.models import User, UserRole
from app.models.organization import DEFAULT_ORGANIZATION_ID


def role_checks(route: APIRoute):
    return [
        dependency.call
        for dependency in route.dependant.dependencies
        if getattr(dependency.call, "__name__", "") == "role_checker"
    ]


PROTECTED_ROUTES = [
    route
    for route in app.routes
    if isinstance(route, APIRoute)
    and route.path not in {
        "/api/v1/health",
        "/api/v1/auth/csrf",
        "/api/v1/auth/config",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/auth/me",
        "/api/v1/auth/forgot-password",
        "/api/v1/auth/codes/request",
        "/api/v1/auth/verify-reset-code",
        "/api/v1/auth/reset-password",
        "/api/v1/auth/register",
        "/api/v1/auth/resend-verification",
        "/api/v1/auth/verify-email",
        "/api/v1/auth/mfa/setup",
        "/api/v1/auth/mfa/enable",
        "/api/v1/auth/mfa/verify-login",
        "/api/v1/admin/invitations/accept",
    }
]


def expected_roles(route: APIRoute) -> set[UserRole]:
    method = next(iter(route.methods))
    if route.path.startswith("/api/v1/admin/") and route.path != "/api/v1/admin/invitations/accept":
        return {UserRole.ADMIN}
    if route.path.startswith(("/api/v1/aiops", "/api/v1/audit")):
        return {UserRole.ADMIN, UserRole.OPERATOR}
    if route.path == "/api/v1/dashboard":
        return set(UserRole)
    if route.path == "/api/v1/documents/upload" or route.path.endswith("/process") or route.path.endswith("/process/retry"):
        return {UserRole.CLINICIAN, UserRole.ADMIN}
    if route.path.startswith("/api/v1/integrations/fhir/push/"):
        return {UserRole.ADMIN}
    if method == "POST" and route.path.startswith("/api/v1/review/"):
        return {UserRole.REVIEWER, UserRole.ADMIN}
    if "/export/" in route.path or route.path.endswith("/fhir"):
        return {UserRole.CLINICIAN, UserRole.REVIEWER, UserRole.ADMIN}
    return set(UserRole)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", list(UserRole))
async def test_every_registered_route_enforces_its_role_dependencies(role):
    user = User(
        id=__import__("uuid").uuid4(),
        email="role-matrix@example.test",
        role=role,
        organization_id=DEFAULT_ORGANIZATION_ID,
    )
    db = AsyncMock()
    db.add = Mock()
    request = Mock(headers={}, client=None, state=SimpleNamespace(request_id="synthetic-request-id"))

    for route in PROTECTED_ROUTES:
        checks = role_checks(route)
        assert checks, f"Missing require_roles dependency on {route.path}"
        declared_roles = next(
            cell.cell_contents
            for cell in checks[-1].__closure__ or ()
            if isinstance(cell.cell_contents, tuple)
            and all(isinstance(item, UserRole) for item in cell.cell_contents)
        )
        assert set(declared_roles) == expected_roles(route), f"Incorrect role policy on {route.path}"
        route_denied = False
        for checker in checks:
            allowed_roles = next(
                cell.cell_contents
                for cell in checker.__closure__ or ()
                if isinstance(cell.cell_contents, tuple)
                and all(isinstance(item, UserRole) for item in cell.cell_contents)
            )
            if role not in allowed_roles:
                route_denied = True
                with pytest.raises(HTTPException) as exc_info:
                    await checker(current_user=user, db=db, request=request)
                assert getattr(exc_info.value, "status_code", None) == 403
            else:
                assert await checker(current_user=user, db=db, request=request) is user

        # Each role is evaluated against every protected route's complete dependency stack.
        assert route_denied == any(
            role not in next(
                cell.cell_contents
                for cell in checker.__closure__ or ()
                if isinstance(cell.cell_contents, tuple)
                and all(isinstance(item, UserRole) for item in cell.cell_contents)
            )
            for checker in checks
        )


def test_route_inventory_requires_auth_or_explicit_public_declaration():
    public_routes = {
        ("GET", "/api/v1/health"),
        ("GET", "/api/v1/auth/csrf"),
        ("GET", "/api/v1/auth/config"),
        ("POST", "/api/v1/auth/login"),
        ("POST", "/api/v1/auth/forgot-password"),
        ("POST", "/api/v1/auth/codes/request"),
        ("POST", "/api/v1/auth/verify-reset-code"),
        ("POST", "/api/v1/auth/reset-password"),
        ("POST", "/api/v1/auth/register"),
        ("POST", "/api/v1/auth/resend-verification"),
        ("POST", "/api/v1/auth/verify-email"),
        ("POST", "/api/v1/auth/mfa/setup"),
        ("POST", "/api/v1/auth/mfa/enable"),
        ("POST", "/api/v1/auth/mfa/verify-login"),
        ("POST", "/api/v1/admin/invitations/accept"),
    }
    csrf_routes = {
        ("POST", "/api/v1/auth/refresh"),
        ("POST", "/api/v1/auth/logout"),
        ("POST", "/api/v1/auth/forgot-password"),
        ("POST", "/api/v1/auth/codes/request"),
        ("POST", "/api/v1/auth/verify-reset-code"),
        ("POST", "/api/v1/auth/reset-password"),
        ("POST", "/api/v1/auth/register"),
        ("POST", "/api/v1/auth/resend-verification"),
        ("POST", "/api/v1/auth/verify-email"),
        ("POST", "/api/v1/auth/mfa/setup"),
        ("POST", "/api/v1/auth/mfa/enable"),
        ("POST", "/api/v1/auth/mfa/verify-login"),
        ("POST", "/api/v1/admin/invitations/accept"),
    }
    for route in (item for item in app.routes if isinstance(item, APIRoute)):
        declarations = {getattr(dependency.call, "__name__", "") for dependency in route.dependant.dependencies}
        for method in route.methods or set():
            key = (method, route.path)
            if key in public_routes:
                continue
            if key in csrf_routes:
                assert "csrf_protect" in declarations, f"Missing CSRF declaration on {route.path}"
            elif route.path == "/api/v1/auth/me":
                assert "get_current_user" in declarations, "Missing authentication on /auth/me"
            else:
                assert "role_checker" in declarations or "get_current_user" in declarations, f"Missing auth declaration on {route.path}"
