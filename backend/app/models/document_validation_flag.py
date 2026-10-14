"""DocumentValidationFlag model — document-level validation outcomes.

Stores validation flags that apply to the whole document rather than
to a single extracted entity. Unlike ValidationResult, there is no
entity_id FK, so flags survive the zero-entity case.

Supersession: when a document is reprocessed, the previous extraction's
flags are retired by setting superseded_at (they are kept for audit).
Active flags have superseded_at IS NULL.
"""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class DocumentValidationFlag(Base):
    __tablename__ = "document_validation_flags"
    __table_args__ = (
        Index("ix_dvf_document_id", "document_id"),
        Index("ix_dvf_extraction_id", "extraction_id"),
        Index("ix_dvf_rule_code", "rule_code"),
        Index(
            "ix_dvf_active",
            "document_id",
            postgresql_where=text("superseded_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    extraction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("extractions.id", ondelete="CASCADE"),
        nullable=False,
    )
    rule_code: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    # 'info' | 'warning' | 'error'
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    # 'pass' | 'warning' | 'fail'
    message: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # e.g. {"vital_term": "blood pressure", "start_offset": 8, "end_offset": 10,
    #        "evidence": "BP not recorded"}
    superseded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # NULL  -> this flag is active (current extraction)
    # set   -> retired by a later reprocessing run
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    document: Mapped["Document"] = relationship(  # type: ignore[name-defined]
        back_populates="validation_flags"
    )
    extraction: Mapped["Extraction"] = relationship(  # type: ignore[name-defined]
        "Extraction"
    )
