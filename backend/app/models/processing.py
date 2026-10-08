"""Processing models — ProcessingJob and ProcessingStep.

ProcessingJob tracks a single pipeline run for a document.
ProcessingStep tracks each named stage within that job.
This is the data source for the AI Operations → Processing Timeline view.
"""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_processing_jobs_status",
        ),
        Index(
            "uq_processing_jobs_one_active_per_document",
            "document_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
            sqlite_where=text("status IN ('queued', 'running')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pipeline_version: Mapped[str | None] = mapped_column(String(32))  # e.g. 'v1.4.2'
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="queued", index=True
    )
    # 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_ms: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    document: Mapped["Document"] = relationship(  # type: ignore[name-defined]
        back_populates="processing_jobs"
    )
    steps: Mapped[list["ProcessingStep"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="ProcessingStep.created_at",
    )
    extractions: Mapped[list["Extraction"]] = relationship(  # type: ignore[name-defined]
        back_populates="processing_job"
    )


class ProcessingStep(Base):
    __tablename__ = "processing_steps"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'skipped')",
            name="ck_processing_steps_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    processing_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("processing_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_name: Mapped[str] = mapped_column(String(64), nullable=False)
    # 'ocr' | 'text_extraction' | 'clinical_extraction'
    # | 'normalization' | 'validation' | 'evidence_linking'
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    # 'pending' | 'running' | 'completed' | 'failed' | 'skipped'
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_ms: Mapped[int | None] = mapped_column(Integer)
    model_version: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    job: Mapped["ProcessingJob"] = relationship(back_populates="steps")
