"""Extraction model — one extraction run per document per processing job."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Extraction(Base):
    __tablename__ = "extractions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    processing_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("processing_jobs.id", ondelete="SET NULL"),
    )
    model_name: Mapped[str | None] = mapped_column(String(128))    # 'claude-sonnet-5'
    model_version: Mapped[str | None] = mapped_column(String(64))  # '2026-09'
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    rejected_entities: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    # 'pending' | 'completed' | 'failed'
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    document: Mapped["Document"] = relationship(  # type: ignore[name-defined]
        back_populates="extractions"
    )
    processing_job: Mapped["ProcessingJob | None"] = relationship(  # type: ignore[name-defined]
        back_populates="extractions"
    )
    entities: Mapped[list["ClinicalEntity"]] = relationship(  # type: ignore[name-defined]
        back_populates="extraction", cascade="all, delete-orphan"
    )
