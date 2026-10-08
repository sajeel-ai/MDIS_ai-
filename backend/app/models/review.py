"""ReviewTask model — human review queue item for a clinical entity."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ReviewTask(Base):
    __tablename__ = "review_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clinical_entities.id", ondelete="SET NULL"),
        index=True,
    )
    priority: Mapped[str] = mapped_column(
        String(16), nullable=False, default="normal", index=True
    )
    # 'high' | 'medium' | 'normal'

    reason: Mapped[str | None] = mapped_column(Text)
    # Human-readable explanation of why this was flagged.

    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", index=True
    )
    # 'pending' | 'in_review' | 'approved' | 'rejected' | 'corrected'

    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision: Mapped[str | None] = mapped_column(String(32))
    # 'approved' | 'rejected' | 'corrected'
    comment: Mapped[str | None] = mapped_column(Text)

    # Relationships
    document: Mapped["Document"] = relationship(  # type: ignore[name-defined]
        back_populates="review_tasks"
    )
    entity: Mapped["ClinicalEntity | None"] = relationship(  # type: ignore[name-defined]
        back_populates="review_tasks"
    )
    assignee: Mapped["User | None"] = relationship(  # type: ignore[name-defined]
        back_populates="review_tasks",
        foreign_keys=[assigned_to],
    )
