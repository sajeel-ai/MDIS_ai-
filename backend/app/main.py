"""
Cognate AI — FastAPI Application Entry Point

D2 scope: application shell + CORS + health endpoint only.
Business API endpoints (documents, cases, review, aiops, etc.) are added in D4.
"""

from contextlib import asynccontextmanager
import logging
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import update

from app.config import settings, validate_fhir_configuration
from app.db import AsyncSessionLocal
from app.models import RefreshToken
from app.security.auth import validate_jwt_configuration
from app.telemetry import install_structured_logging, metrics
from app.routers import health


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup / shutdown lifecycle."""
    validate_jwt_configuration()
    validate_fhir_configuration()
    # A process restart starts a new authentication epoch. Revoking all
    # refresh-token families also invalidates the short-lived access cookies,
    # because authenticated requests verify their family is still active.
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await session.commit()
    # Nothing to initialize in D2 beyond the DB engine (created at import time).
    yield
    # Graceful engine disposal on shutdown.
    from app.db import engine
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Cognate AI — Clinical Document Intelligence API",
    docs_url=f"{settings.api_prefix}/docs",
    redoc_url=f"{settings.api_prefix}/redoc",
    openapi_url=f"{settings.api_prefix}/openapi.json",
    lifespan=lifespan,
)
install_structured_logging()
security_logger = logging.getLogger("app.security")


@app.middleware("http")
async def security_headers_and_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    started = datetime.now(timezone.utc)
    try:
        response = await call_next(request)
    except Exception:
        security_logger.exception(
            "Unhandled request failure",
            extra={"request_id": request_id, "telemetry_event": "request_failure"},
        )
        response = JSONResponse(status_code=500, content={"detail": "Internal server error"})
    response.headers["X-Request-ID"] = request_id
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'; base-uri 'self'; object-src 'none'"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["X-Frame-Options"] = "DENY"
    content_type = response.headers.get("content-type", "")
    if content_type.startswith("application/json") and "charset=" not in content_type.lower():
        response.headers["Content-Type"] = "application/json; charset=utf-8"
    if request.url.path.startswith(f"{settings.api_prefix}/"):
        response.headers["Cache-Control"] = "no-store, private"
    if settings.auth_cookie_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    route = request.scope.get("route")
    route_name = getattr(route, "path", request.url.path)
    metrics.observe_request(
        request.method,
        route_name,
        response.status_code,
        (datetime.now(timezone.utc) - started).total_seconds(),
    )
    security_logger.info(
        "request_complete",
        extra={
            "telemetry_event": "request_complete",
            "request_id": request_id,
            "user_id": getattr(request.state, "user_id", None),
            "organization_id": getattr(request.state, "organization_id", None),
        },
    )
    return response


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(_request: Request, _exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": "Invalid request"})


@app.exception_handler(Exception)
async def generic_server_error_handler(_request: Request, _exc: Exception):
    # Avoid returning or logging exception details that could contain PHI or credentials.
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

# ---------------------------------------------------------------------------
# CORS — allow explicit origins from configuration allowlist (no wildcards)
# ---------------------------------------------------------------------------
cors_origins = settings.cors_origins_list
if not cors_origins or any(origin == "*" for origin in cors_origins):
    raise RuntimeError("CORS_ORIGINS must be a non-empty explicit origin allowlist; wildcard '*' is forbidden")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Request-ID"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
from app.routers import health, dashboard, documents, processing, review, aiops, patients, audit, auth, integrations, admin_auth, notifications, search, settings as settings_router

app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(dashboard.router, prefix=settings.api_prefix)
app.include_router(documents.router, prefix=settings.api_prefix)
app.include_router(processing.router, prefix=settings.api_prefix)
app.include_router(review.router, prefix=settings.api_prefix)
app.include_router(aiops.router, prefix=settings.api_prefix)
app.include_router(patients.router, prefix=settings.api_prefix)
app.include_router(audit.router, prefix=settings.api_prefix)
app.include_router(integrations.router, prefix=settings.api_prefix)
app.include_router(admin_auth.router, prefix=settings.api_prefix)
app.include_router(notifications.router, prefix=settings.api_prefix)
app.include_router(search.router, prefix=settings.api_prefix)
app.include_router(settings_router.router, prefix=settings.api_prefix)
