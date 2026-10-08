"""
Cognate AI — Async Database Layer

Creates a single AsyncEngine and async_sessionmaker at module load time.
One engine per process — never create a new engine per request.

Usage (in routers via FastAPI Depends):

    from app.db import get_db

    async def my_endpoint(db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(Patient))
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import event, false
from sqlalchemy.orm import DeclarativeBase, Session, with_loader_criteria

from app.config import settings

# ---------------------------------------------------------------------------
# Engine — shared across all requests
# ---------------------------------------------------------------------------
engine = create_async_engine(
    settings.database_url,
    # SQL parameters may contain clinical data; never echo them to logs.
    echo=False,
    # Pool settings appropriate for a single-process dev server.
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,   # Re-validate connections before use
)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# ---------------------------------------------------------------------------
# Declarative base — all ORM models inherit from this
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass


@event.listens_for(Session, "do_orm_execute")
def apply_organization_scope(execute_state) -> None:
    """Apply tenant criteria to ORM reads once authentication sets the session scope."""
    organization_id = execute_state.session.info.get("organization_id")
    if not execute_state.is_select:
        return

    if organization_id is None:
        if (
            execute_state.session.info.get("allow_unscoped_user_lookup")
            or execute_state.session.info.get("allow_unscoped_refresh_lookup")
            or execute_state.session.info.get("allow_unscoped_job_lookup")
        ):
            return
        if execute_state.session.info.get("scope_required") and execute_state.all_mappers:
            execute_state.statement = execute_state.statement.where(false())
        return

    from app.models import (
        AuditEvent,
        ClinicalEntity,
        Document,
        Encounter,
        EvidenceSpan,
        Extraction,
        IcdCode,
        Patient,
        ProcessingJob,
        ReviewTask,
        User,
        ValidationResult,
    )

    criteria = (
        with_loader_criteria(User, User.organization_id == organization_id, include_aliases=True),
        with_loader_criteria(Patient, Patient.organization_id == organization_id, include_aliases=True),
        with_loader_criteria(Document, Document.organization_id == organization_id, include_aliases=True),
        with_loader_criteria(AuditEvent, AuditEvent.organization_id == organization_id, include_aliases=True),
        with_loader_criteria(Encounter, Encounter.patient.has(Patient.organization_id == organization_id), include_aliases=True),
        with_loader_criteria(IcdCode, IcdCode.encounter.has(Encounter.patient.has(Patient.organization_id == organization_id)), include_aliases=True),
        with_loader_criteria(ProcessingJob, ProcessingJob.document.has(Document.organization_id == organization_id), include_aliases=True),
        with_loader_criteria(ReviewTask, ReviewTask.document.has(Document.organization_id == organization_id), include_aliases=True),
        with_loader_criteria(Extraction, Extraction.document.has(Document.organization_id == organization_id), include_aliases=True),
        with_loader_criteria(ClinicalEntity, ClinicalEntity.extraction.has(Extraction.document.has(Document.organization_id == organization_id)), include_aliases=True),
        with_loader_criteria(EvidenceSpan, EvidenceSpan.entity.has(ClinicalEntity.extraction.has(Extraction.document.has(Document.organization_id == organization_id))), include_aliases=True),
        with_loader_criteria(ValidationResult, ValidationResult.entity.has(ClinicalEntity.extraction.has(Extraction.document.has(Document.organization_id == organization_id))), include_aliases=True),
    )
    execute_state.statement = execute_state.statement.options(*criteria)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session, committing on success and
    rolling back on exception."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
