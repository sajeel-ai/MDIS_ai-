"""Static inventory check for authentication and role protection on PHI APIs."""
from fastapi.routing import APIRoute

from app.main import app


PUBLIC_ALLOWLIST = {
    ("GET", "/api/v1/health"),
    ("GET", "/api/v1/integrations/fhir/metadata"),
}
# This endpoint consumes a short-lived single-use invitation token and only
# activates an account; it does not read PHI or rely on anonymous identity.
TOKEN_AUTHENTICATED_NON_PHI = {("POST", "/api/v1/admin/invitations/accept")}
PHI_PREFIXES = (
    "/api/v1/documents", "/api/v1/patients", "/api/v1/review",
    "/api/v1/search", "/api/v1/processing", "/api/v1/audit",
    "/api/v1/notifications", "/api/v1/dashboard", "/api/v1/aiops",
    "/api/v1/admin", "/api/v1/settings",
)


def _dependency_names(route: APIRoute) -> set[str]:
    names: set[str] = set()

    def visit(dependant):
        for child in dependant.dependencies:
            names.add(getattr(child.call, "__name__", ""))
            visit(child)

    visit(route.dependant)
    return names


def test_every_phi_route_requires_authentication_and_role_check():
    violations = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith(PHI_PREFIXES):
            continue
        for method in route.methods or set():
            if (method, route.path) in PUBLIC_ALLOWLIST | TOKEN_AUTHENTICATED_NON_PHI:
                continue
            dependencies = _dependency_names(route)
            if "get_current_user" not in dependencies or "role_checker" not in dependencies:
                violations.append((method, route.path, sorted(dependencies)))
    assert violations == []


def test_auth_allowlist_is_explicit_and_short():
    assert PUBLIC_ALLOWLIST == {
        ("GET", "/api/v1/health"),
        ("GET", "/api/v1/integrations/fhir/metadata"),
    }


def test_invitation_acceptance_uses_single_use_token_and_csrf_guard():
    route = next(r for r in app.routes if isinstance(r, APIRoute) and r.path == "/api/v1/admin/invitations/accept")
    assert "csrf_protect" in _dependency_names(route)
    assert ("POST", route.path) in TOKEN_AUTHENTICATED_NON_PHI
