"""Retention policy and purge service.

Calculates retention eligibility while preserving the database's
append-only audit boundary.
"""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.audit import AuditEvent
from app.models.processing import ProcessingJob
from app.services.audit_service import record_audit_event


class RetentionPurgeBlockedError(RuntimeError):
    """Raised when the database's append-only audit boundary blocks deletion."""


class RetentionPurgeService:
    def __init__(self, session: AsyncSession):
        self.session = session

    def get_retention_policy(self) -> Dict[str, Any]:
        """Return the current active retention policy configuration."""
        return {
            "audit_log_retention_days": max(settings.retention_audit_log_days, 2192),
            "audit_log_minimum_retention_days": 2192,
            "scratchpad_retention_days": settings.retention_scratchpad_days,
            "policy_enforced": True,
        }

    async def run_retention_purge(self, dry_run: bool = True) -> Dict[str, Any]:
        """Preview or purge scratchpad jobs; audit-log deletion is never executed here."""
        now = datetime.now(timezone.utc)
        audit_cutoff = now - timedelta(days=max(settings.retention_audit_log_days, 2192))
        scratchpad_cutoff = now - timedelta(days=settings.retention_scratchpad_days)

        # 1. Count expired audit logs older than the retention floor, excluding holds.
        eligible_audit = select(AuditEvent.id).where(
            AuditEvent.created_at < audit_cutoff,
            AuditEvent.legal_hold.is_(False),
        )
        audit_count = (await self.session.execute(
            select(func.count()).select_from(eligible_audit.subquery())
        )).scalar() or 0

        # 2. Count failed / cancelled processing jobs older than the scratchpad window.
        scratch_count = (await self.session.execute(
            select(func.count()).select_from(
                select(ProcessingJob.id).where(
                    ProcessingJob.status.in_(["failed", "cancelled"]),
                    ProcessingJob.created_at < scratchpad_cutoff,
                ).subquery()
            )
        )).scalar() or 0

        # Only expired failed/cancelled processing scratchpad jobs are mutable.
        # AuditEvent rows are counted for preview and never deleted by this code.
        purged_scratch = 0
        if not dry_run:
            result = await self.session.execute(
                delete(ProcessingJob).where(
                    ProcessingJob.status.in_(["failed", "cancelled"]),
                    ProcessingJob.created_at < scratchpad_cutoff,
                )
            )
            purged_scratch = int(getattr(result, "rowcount", 0) or 0)
            await self.session.commit()

        return {
            "status": "dry_run" if dry_run else "completed",
            "dry_run": dry_run,
            "audit_logs_purged": 0,
            "audit_logs_eligible": audit_count,
            "scratchpad_records_purged": purged_scratch,
            "scratchpad_records_eligible": scratch_count,
            "audit_cutoff": audit_cutoff.isoformat(),
            "scratchpad_cutoff": scratchpad_cutoff.isoformat(),
        }

    async def place_legal_hold(
        self, audit_event_id: uuid.UUID, *, user_id: uuid.UUID, organization_id: uuid.UUID
    ) -> bool:
        """Set a permanent hold; the database trigger prevents clearing it."""
        result = await self.session.execute(
            update(AuditEvent)
            .where(AuditEvent.id == audit_event_id, AuditEvent.legal_hold.is_(False))
            .values(legal_hold=True)
        )
        if not getattr(result, "rowcount", 0):
            existing_hold = await self.session.scalar(
                select(AuditEvent.legal_hold).where(AuditEvent.id == audit_event_id)
            )
            if existing_hold is None:
                return False
            if existing_hold:
                return True
        await record_audit_event(
            self.session,
            action="legal_hold_applied",
            user_id=user_id,
            organization_id=organization_id,
            resource_type="audit_event",
            resource_id=audit_event_id,
            metadata={"legal_hold": True},
        )
        await self.session.commit()
        return True

