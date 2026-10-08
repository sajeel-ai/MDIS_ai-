"""ClinicalEntity model — a single extracted clinical fact."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ClinicalEntity(Base):
    __tablename__ = "clinical_entities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    extraction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("extractions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # 'diagnosis' | 'medication' | 'symptom' | 'procedure' | 'lab_result' | 'temporal'

    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    # The original text as extracted by the model.

    normalized_value: Mapped[str | None] = mapped_column(Text)
    original_ai_value: Mapped[str | None] = mapped_column(Text)
    # The standardized/normalized form (e.g., SNOMED preferred term).

    confidence: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    # 0.0000 – 1.0000

    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unreviewed", index=True
    )
    assertion: Mapped[str] = mapped_column(String(24), nullable=False, default="present", server_default="present")
    section: Mapped[str | None] = mapped_column(String(64))
    # 'unreviewed' | 'approved' | 'rejected' | 'needs_correction'

    # Entity-type-specific fields stored as JSONB.
    # Examples:
    #   diagnosis:   { "code": "J44.1", "code_system": "ICD-10", "status": "Active" }
    #   medication:  { "dose": "500 mg", "frequency": "Once daily", "route": "Oral" }
    #   lab_result:  { "value": "7.2", "unit": "mmol/L", "is_abnormal": true }
    details: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    extraction: Mapped["Extraction"] = relationship(  # type: ignore[name-defined]
        back_populates="entities"
    )
    evidence_spans: Mapped[list["EvidenceSpan"]] = relationship(  # type: ignore[name-defined]
        back_populates="entity", cascade="all, delete-orphan"
    )
    validation_results: Mapped[list["ValidationResult"]] = relationship(  # type: ignore[name-defined]
        back_populates="entity", cascade="all, delete-orphan"
    )
    review_tasks: Mapped[list["ReviewTask"]] = relationship(  # type: ignore[name-defined]
        back_populates="entity"
    )
