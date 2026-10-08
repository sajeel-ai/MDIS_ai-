"""User model."""
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym, validates

from app.db import Base
from app.models.roles import UserRole
from app.models.organization import DEFAULT_ORGANIZATION_ID


class RegistrationStatus(str, Enum):
    PENDING_EMAIL_VERIFICATION = "pending_email_verification"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False,
        index=True, default=DEFAULT_ORGANIZATION_ID,
    )
    email: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(128))
    role: Mapped[UserRole] = mapped_column(
        SAEnum(
            UserRole,
            native_enum=False,
            values_callable=lambda roles: [role.value for role in roles],
            length=32,
            create_constraint=False,
        ),
        nullable=False,
        default=UserRole.REVIEWER,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    failed_login_count: Mapped[int] = mapped_column(default=0, nullable=False, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pending_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    registration_status: Mapped[str] = mapped_column(String(32), nullable=False, default=RegistrationStatus.APPROVED.value, server_default=RegistrationStatus.APPROVED.value)
    professional_role_requested: Mapped[str | None] = mapped_column(String(32), nullable=True)
    license_or_certification_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    license_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requested_organization_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    terms_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    mfa_secret_encrypted: Mapped[str | None] = mapped_column(String(512), nullable=True)
    recovery_code_hashes: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    # Keep the existing database/API field while exposing the requested domain name.
    full_name = synonym("display_name")

    @validates("email")
    def normalize_email(self, _key: str, value: str) -> str:
        return value.strip().lower()

    # Relationships
    review_tasks: Mapped[list["ReviewTask"]] = relationship(  # type: ignore[name-defined]
        back_populates="assignee", foreign_keys="ReviewTask.assigned_to"
    )
    audit_events: Mapped[list["AuditEvent"]] = relationship(  # type: ignore[name-defined]
        back_populates="user"
    )
