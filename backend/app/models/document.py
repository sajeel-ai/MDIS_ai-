"""Document model.

Note: source_text is NOT stored here. It lives in DocumentVersion to support
OCR re-runs and text versioning with full provenance.
"""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.organization import DEFAULT_ORGANIZATION_ID


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_org_lifecycle_filters", "organization_id", "status", "review_status", "updated_at"),
        CheckConstraint(
            "status IN ('uploaded', 'queued', 'processing', 'completed', 'failed')",
            name="ck_documents_processing_status",
        ),
        CheckConstraint(
            "review_status IN ('not_required', 'pending', 'in_review', 'approved', 'rejected')",
            name="ck_documents_review_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False,
        index=True, default=DEFAULT_ORGANIZATION_ID,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    encounter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("encounters.id", ondelete="SET NULL"),
        index=True,
    )
    document_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # 'discharge_summary' | 'progress_note' | 'radiology_report' | 'emergency_note'
    # | 'consultation_report' | 'operative_report' | 'lab_report'

    source: Mapped[str] = mapped_column(String(32), nullable=False)
    # 'upload' | 'mimic_demo' | 'mimic_note' | 'synthetic'

    file_name: Mapped[str | None] = mapped_column(String(256))
    mime_type: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int | None] = mapped_column(Integer)

    # Storage key — path-agnostic from day one.
    # Phase 2 format: "local:documents/{id}/file.pdf"
    # Future S3 format: "s3:cognate-documents/{id}/file.pdf"
    storage_key: Mapped[str | None] = mapped_column(String(512))

    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="uploaded", server_default="uploaded", index=True
    )
    # Processing lifecycle only: uploaded | queued | processing | completed | failed
    review_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="not_required", server_default="not_required", index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    patient: Mapped["Patient"] = relationship(  # type: ignore[name-defined]
        back_populates="documents"
    )
    encounter: Mapped["Encounter | None"] = relationship(  # type: ignore[name-defined]
        back_populates="documents"
    )
    versions: Mapped[list["DocumentVersion"]] = relationship(  # type: ignore[name-defined]
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentVersion.version_number"
    )
    processing_jobs: Mapped[list["ProcessingJob"]] = relationship(  # type: ignore[name-defined]
        back_populates="document", cascade="all, delete-orphan"
    )
    extractions: Mapped[list["Extraction"]] = relationship(  # type: ignore[name-defined]
        back_populates="document", cascade="all, delete-orphan"
    )
    review_tasks: Mapped[list["ReviewTask"]] = relationship(  # type: ignore[name-defined]
        back_populates="document", cascade="all, delete-orphan"
    )
