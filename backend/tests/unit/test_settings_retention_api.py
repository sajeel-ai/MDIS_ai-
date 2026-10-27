"""Unit tests for Settings Retention endpoints."""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.db import get_db
from app.dependencies.auth import UserContext, UserRole, get_current_user


@pytest.mark.asyncio
async def test_get_retention_policy_endpoint():
    user = UserContext(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        role=UserRole.ADMIN,
        email="admin@cognate.test",
    )
    mock_db = AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.get("/api/v1/settings/retention-policy")
            assert res.status_code == 200
            data = res.json()
            assert "audit_log_retention_days" in data
            assert "scratchpad_retention_days" in data
            assert data["policy_enforced"] is True
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_trigger_retention_purge_endpoint_admin_success():
    user = UserContext(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        role=UserRole.ADMIN,
        email="admin@cognate.test",
    )
    mock_db = AsyncMock()
    added_events = []
    mock_db.add = MagicMock(side_effect=added_events.append)

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_db

    fake_result = {
        "status": "dry_run",
        "dry_run": True,
        "audit_logs_purged": 0,
        "audit_logs_eligible": 10,
        "scratchpad_records_purged": 0,
        "scratchpad_records_eligible": 3,
        "audit_cutoff": "2020-01-01T00:00:00Z",
        "scratchpad_cutoff": "2026-09-01T00:00:00Z",
    }

    try:
        with patch("app.routers.settings.RetentionPurgeService") as MockService:
            instance = MockService.return_value
            instance.run_retention_purge = AsyncMock(return_value=fake_result)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.post("/api/v1/settings/retention/purge")
                assert res.status_code == 200
                data = res.json()
                assert data["status"] == "dry_run"
                assert data["audit_logs_eligible"] == 10
                assert data["scratchpad_records_eligible"] == 3
                assert instance.run_retention_purge.called
                assert instance.run_retention_purge.call_args.kwargs["dry_run"] is True
                from app.models import AuditEvent
                assert any(
                    isinstance(event, AuditEvent) and event.action == "retention_purge_requested"
                    for event in added_events
                )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_trigger_retention_purge_endpoint_non_admin_forbidden():
    user = UserContext(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        role=UserRole.VIEWER,
        email="viewer@cognate.test",
    )
    mock_db = AsyncMock()
    mock_db.add = MagicMock()

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.post("/api/v1/settings/retention/purge")
            assert res.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_live_retention_purge_runs_scratchpad_cleanup_without_deleting_audit_rows():
    user = UserContext(id=uuid.uuid4(), organization_id=uuid.uuid4(), role=UserRole.ADMIN, email="admin@cognate.test")
    db = AsyncMock()
    db.add = MagicMock()
    count_audit, count_scratch, deleted = MagicMock(), MagicMock(), MagicMock()
    count_audit.scalar.return_value = 0
    count_scratch.scalar.return_value = 0
    deleted.rowcount = 0
    async def execute_for_purge(statement):
        text = str(statement).lower()
        if "audit_events" in text:
            return count_audit
        if text.lstrip().startswith("select"):
            return count_scratch
        return deleted
    db.execute = AsyncMock(side_effect=execute_for_purge)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.post("/api/v1/settings/retention/purge?dry_run=false")
            assert res.status_code == 200
            assert res.json()["status"] == "completed"
            assert res.json()["audit_logs_purged"] == 0
            assert res.json()["scratchpad_records_purged"] == 0
            assert "processing_jobs" in str(db.execute.await_args_list[-1].args[0])
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_can_apply_permanent_audit_legal_hold():
    event_id = uuid.uuid4()
    user = UserContext(id=uuid.uuid4(), organization_id=uuid.uuid4(), role=UserRole.ADMIN, email="admin@cognate.test")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    try:
        with patch("app.routers.settings.RetentionPurgeService") as MockService:
            instance = MockService.return_value
            instance.place_legal_hold = AsyncMock(return_value=True)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.post(f"/api/v1/settings/audit-events/{event_id}/legal-hold")
            assert res.status_code == 200
            assert res.json()["legal_hold"] is True
            instance.place_legal_hold.assert_awaited_once()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_retention_purge_blocked_when_anonymous_access_enabled(monkeypatch):
    user = UserContext(id=uuid.uuid4(), organization_id=uuid.uuid4(), role=UserRole.ADMIN, email="admin@cognate.test")
    app.dependency_overrides[get_current_user] = lambda: user
    monkeypatch.setattr("app.routers.settings.settings.allow_anonymous_access", True)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.post("/api/v1/settings/retention/purge")
            assert res.status_code == 403
            assert "anonymous access" in res.json()["detail"]
    finally:
        app.dependency_overrides.clear()
