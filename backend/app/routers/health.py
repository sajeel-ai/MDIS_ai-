"""Health and internal telemetry endpoints.

GET /api/v1/health

Performs a real SELECT 1 against the database so the health check is
meaningful during Docker/backend startup verification. Returns HTTP 503
if the database is unreachable.
"""

import ipaddress
from pathlib import Path

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text

from app.db import AsyncSessionLocal
from app.db import engine
from app.config import settings
from app.telemetry import metrics, render_metrics

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


@router.get("/live", summary="Liveness probe")
async def liveness_check():
    return {"status": "ok", "service": "cognate-ai-api"}


@router.get("/ready", summary="Readiness probe")
async def readiness_check():
    checks = {"database": False, "storage": False, "queue": False}
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
            await session.execute(text("SELECT 1 FROM processing_jobs LIMIT 1"))
        checks["database"] = True
        checks["queue"] = True
    except Exception:
        pass
    storage_path = Path(settings.storage_local_path)
    checks["storage"] = settings.storage_backend.lower() != "local" or storage_path.is_dir()
    ready = all(checks.values())
    return JSONResponse(
        status_code=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "ready" if ready else "not_ready", "checks": checks},
    )


@router.get("/metrics", summary="Internal Prometheus metrics")
async def metrics_endpoint(request: Request):
    if settings.metrics_internal_only:
        client_host = request.client.host if request.client else ""
        try:
            address = ipaddress.ip_address(client_host)
        except ValueError:
            return JSONResponse(status_code=403, content={"detail": "Metrics are internal-only"})
        if not (address.is_loopback or address.is_private):
            return JSONResponse(status_code=403, content={"detail": "Metrics are internal-only"})
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text(
                    """
                    SELECT
                      count(*) FILTER (WHERE status IN ('queued', 'running')) AS queue_depth,
                      count(*) FILTER (WHERE status = 'failed') AS failed_jobs,
                      EXTRACT(EPOCH FROM (
                        CURRENT_TIMESTAMP - MIN(created_at) FILTER (WHERE status IN ('queued', 'running'))
                      )) AS oldest_job_age_seconds,
                      (SELECT count(*) FROM review_tasks WHERE status IN ('pending', 'in_review')) AS review_backlog
                    FROM processing_jobs
                    """
                )
            )
            row = result.one()
            metrics.set_gauge("queue_depth", row.queue_depth or 0)
            metrics.set_gauge("failed_jobs", row.failed_jobs or 0)
            metrics.set_gauge("queue_oldest_job_age_seconds", row.oldest_job_age_seconds or 0)
            metrics.set_gauge("review_backlog", row.review_backlog or 0)
            stage_rows = await session.execute(
                text(
                    """
                    SELECT step_name, AVG(processing_ms) AS average_ms
                    FROM processing_steps
                    WHERE processing_ms IS NOT NULL
                    GROUP BY step_name
                    """
                )
            )
            for stage, average_ms in stage_rows:
                metrics.set_gauge(
                    "processing_stage_duration_ms",
                    average_ms or 0,
                    labels={"stage": stage},
                )
    except Exception:
        metrics.increment("database_errors_total", labels={"operation": "metrics_refresh"})
    pool = getattr(engine.sync_engine, "pool", None)
    if pool is not None and hasattr(pool, "checkedout"):
        metrics.set_gauge("db_pool_checked_out", pool.checkedout())
        metrics.set_gauge("db_pool_size", pool.size())
    for metric_name in (
        "dead_letter_jobs",
        "ocr_errors_total",
        "ocr_duration_seconds",
        "extraction_provider_errors_total",
        "extraction_fallbacks_total",
        "audit_write_failures_total",
        "storage_errors_total",
        "backup_age_seconds",
    ):
        metrics.set_gauge(metric_name, 0)
    return Response(content=render_metrics(), media_type="text/plain; version=0.0.4")
