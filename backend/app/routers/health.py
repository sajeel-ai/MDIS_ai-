"""Health router — D2 verification endpoint.

GET /api/v1/health

Performs a real SELECT 1 against the database so the health check is
meaningful during Docker/backend startup verification. Returns HTTP 503
if the database is unreachable.
"""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db import AsyncSessionLocal

router = APIRouter(tags=["health"])


@router.get("/health", summary="Service and database health check")
async def health_check():
    """
    Returns service status and a real database connectivity check.

    - **status**: `"ok"` if all systems healthy, `"degraded"` otherwise
    - **database**: `"connected"` if SELECT 1 succeeds, `"unreachable"` if not
    """
    db_status = "unreachable"
    http_status = status.HTTP_503_SERVICE_UNAVAILABLE

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        db_status = "connected"
        http_status = status.HTTP_200_OK
    except Exception as exc:
        db_status = f"unreachable: {type(exc).__name__}"

    return JSONResponse(
        status_code=http_status,
        content={
            "status": "ok" if db_status == "connected" else "degraded",
            "service": "cognate-ai-api",
            "database": db_status,
        },
    )
