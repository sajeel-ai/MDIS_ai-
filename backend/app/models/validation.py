"""ValidationResult model — per-rule validation outcome for a clinical entity."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ValidationResult(Base):
    __tablename__ = "validation_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clinical_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    validation_rule: Mapped[str] = mapped_column(String(128), nullable=False)
    rule_code: Mapped[str | None] = mapped_column(String(64), index=True)
    # e.g. 'schema_validation' | 'required_fields' | 'evidence_required'
    #      | 'confidence_threshold' | 'terminology_normalization'

    status: Mapped[str] = mapped_column(String(16), nullable=False)
    # 'pass' | 'fail' | 'warning'

    severity: Mapped[str | None] = mapped_column(String(16))
    # 'info' | 'warning' | 'error'

    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    entity: Mapped["ClinicalEntity"] = relationship(  # type: ignore[name-defined]
        back_populates="validation_results"
    )
