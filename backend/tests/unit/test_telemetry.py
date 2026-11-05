import io
import json
import logging
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.telemetry import (
    JsonLogFormatter,
    RedactionFilter,
    metrics,
    render_metrics,
)


def test_structured_logs_never_emit_synthetic_phi():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(RedactionFilter())
    handler.setFormatter(JsonLogFormatter())
    logger = logging.getLogger("telemetry.synthetic")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False

    logger.info(
        "patient=%s mrn=%s note=%s filename=%s",
        "Alice Example",
        "MRN-123456",
        "Start insulin if glucose > 200",
        "alice-example-note.txt",
        extra={"request_id": "req-123", "user_id": "user-456", "organization_id": "org-789"},
    )

    payload = json.loads(stream.getvalue())
    output = stream.getvalue()
    assert "Alice Example" not in output
    assert "MRN-123456" not in output
    assert "Start insulin" not in output
    assert "alice-example-note.txt" not in output
    assert payload["request_id"] == "req-123"
    assert payload["user_id"] == "user-456"
    assert payload["organization_id"] == "org-789"


def test_metrics_use_allowlisted_labels_and_render_prometheus():
    metrics.reset()
    metrics.observe_request("GET", "/api/v1/health", 200, 0.02)
    metrics.increment("storage_errors_total", labels={"operation": "read"})
    metrics.increment(
        "storage_errors_total",
        labels={"operation": "MRN-123456", "result": "patient note filename.txt"},
    )
    metrics.set_gauge("queue_depth", 3)

    output = render_metrics()

    assert "http_requests_total{method=\"GET\",route=\"/api/v1/health\",status=\"200\"} 1" in output
    assert "storage_errors_total{operation=\"read\"} 1" in output
    assert "queue_depth 3" in output
    assert "MRN-123456" not in output
    assert "filename.txt" not in output
    assert "Alice" not in output


@pytest.mark.asyncio
async def test_readiness_reports_database_failure(monkeypatch, tmp_path: Path):
    from app.routers.health import readiness_check

    class BrokenSession:
        async def __aenter__(self):
            raise RuntimeError("synthetic database failure with MRN-123456")

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr("app.routers.health.AsyncSessionLocal", lambda: BrokenSession())
    monkeypatch.setattr("app.config.settings.storage_local_path", str(tmp_path))

    response = await readiness_check()

    assert response.status_code == 503
    body = response.body.decode()
    assert "database" in body
    assert "MRN-123456" not in body


@pytest.mark.asyncio
async def test_metrics_appear_after_synthetic_traffic(monkeypatch):
    from app.main import app

    class BrokenSession:
        async def __aenter__(self):
            raise RuntimeError("synthetic database failure")

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr("app.routers.health.AsyncSessionLocal", lambda: BrokenSession())
    metrics.reset()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        await client.get("/api/v1/live")
        response = await client.get("/api/v1/metrics")

    assert response.status_code == 200
    assert "http_requests_total" in response.text
    assert "route=\"/api/v1/live\"" in response.text
    assert "synthetic" not in response.text
