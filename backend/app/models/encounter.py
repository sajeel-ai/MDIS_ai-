"""Encounter model."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Encounter(Base):
    __tablename__ = "encounters"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # MIMIC-IV hadm_id or other source encounter identifier.
    external_encounter_id: Mapped[str | None] = mapped_column(String(64), index=True)
    admit_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discharge_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Computed: (discharge_time - admit_time) in hours. Stored for fast querying.
    los_hours: Mapped[float | None] = mapped_column(Numeric(8, 2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    patient: Mapped["Patient"] = relationship(  # type: ignore[name-defined]
        back_populates="encounters"
    )
    icd_codes: Mapped[list["IcdCode"]] = relationship(  # type: ignore[name-defined]
        back_populates="encounter", cascade="all, delete-orphan"
    )
    documents: Mapped[list["Document"]] = relationship(  # type: ignore[name-defined]
        back_populates="encounter"
    )
