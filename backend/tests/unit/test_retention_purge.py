"""Unit tests for retention policy and purge job — Item 3."""
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from app.services.retention.retention_service import RetentionPurgeBlockedError, RetentionPurgeService


def test_audit_retention_floor_is_at_least_six_years():
    from pydantic import ValidationError
    from app.config import Settings

    with pytest.raises(ValidationError):
        Settings(retention_audit_log_days=2191)


@pytest.mark.asyncio
async def test_retention_service_policy_returns_configured_days():
    """Verify retention service exposes configured policy parameters."""
    session = AsyncMock()
    service = RetentionPurgeService(session)

    with patch("app.services.retention.retention_service.settings") as mock_settings:
        mock_settings.retention_audit_log_days = 2555
        mock_settings.retention_scratchpad_days = 30

        policy = service.get_retention_policy()
        assert policy["audit_log_retention_days"] == 2555
        assert policy["scratchpad_retention_days"] == 30


@pytest.mark.asyncio
async def test_live_retention_purge_deletes_only_expired_scratchpad_jobs():
    """Live purge may delete expired failed jobs but never audit events."""
    session = AsyncMock()
    count_audit, count_scratch, deleted = MagicMock(), MagicMock(), MagicMock()
    count_audit.scalar.return_value = 0
    count_scratch.scalar.return_value = 2
    deleted.rowcount = 2
    session.execute.side_effect = [count_audit, count_scratch, deleted]
    with patch("app.services.retention.retention_service.settings") as mock_settings:
        mock_settings.retention_audit_log_days = 2192
        mock_settings.retention_scratchpad_days = 30
        result = await RetentionPurgeService(session).run_retention_purge(dry_run=False)
    assert result["status"] == "completed"
    assert result["audit_logs_purged"] == 0
    assert result["scratchpad_records_purged"] == 2
    delete_stmt = session.execute.await_args_list[2].args[0]
    assert "processing_jobs" in str(delete_stmt)
    assert "audit_events" not in str(delete_stmt)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_retention_dry_run_is_default_and_never_executes_deletes():
    session = AsyncMock()
    count_audit, count_scratch = MagicMock(), MagicMock()
    count_audit.scalar.return_value = 3
    count_scratch.scalar.return_value = 2
    session.execute.side_effect = [count_audit, count_scratch]

    with patch("app.services.retention.retention_service.settings") as mock_settings:
        mock_settings.retention_audit_log_days = 100
        mock_settings.retention_scratchpad_days = 30
        result = await RetentionPurgeService(session).run_retention_purge()

    assert result["dry_run"] is True
    assert result["status"] == "dry_run"
    assert result["audit_logs_purged"] == 0
    assert result["audit_logs_eligible"] == 3
    assert result["scratchpad_records_purged"] == 0
    assert result["scratchpad_records_eligible"] == 2
    assert session.execute.await_count == 2
    session.commit.assert_not_awaited()

