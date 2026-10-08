"""EvidenceSpan model — character-level evidence link from entity to source text.

One entity can have multiple evidence spans (e.g., a diagnosis mentioned in
two separate sections of a note). Each span points to a specific DocumentVersion
to maintain exact provenance even across OCR re-runs.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class EvidenceSpan(Base):
    __tablename__ = "evidence_spans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clinical_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id"),
        nullable=False,
        index=True,
    )
    page_number: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # The exact characters raw_text[start_offset:end_offset] — stored for
    # fast retrieval without re-slicing the full text.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    entity: Mapped["ClinicalEntity"] = relationship(  # type: ignore[name-defined]
        back_populates="evidence_spans"
    )
    document_version: Mapped["DocumentVersion"] = relationship(  # type: ignore[name-defined]
        back_populates="evidence_spans"
    )
