"""Add email verification and organization-scoped registration approval."""

from alembic import op
import sqlalchemy as sa


revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("users", sa.Column("registration_status", sa.String(length=32), nullable=False, server_default="approved"))
    op.add_column("users", sa.Column("professional_role_requested", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("license_or_certification_number", sa.String(length=128), nullable=True))
    op.add_column("users", sa.Column("license_type", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("requested_organization_name", sa.String(length=128), nullable=True))
    op.add_column("users", sa.Column("phone", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("rejection_reason", sa.String(length=500), nullable=True))
    op.execute(sa.text("UPDATE users SET registration_status = 'pending_approval' WHERE pending_approval = true"))
    op.create_index("ix_users_registration_org_status", "users", ["organization_id", "registration_status"])


def downgrade() -> None:
    op.drop_index("ix_users_registration_org_status", table_name="users")
    op.drop_column("users", "rejection_reason")
    op.drop_column("users", "terms_accepted_at")
    op.drop_column("users", "phone")
    op.drop_column("users", "requested_organization_name")
    op.drop_column("users", "license_type")
    op.drop_column("users", "license_or_certification_number")
    op.drop_column("users", "professional_role_requested")
    op.drop_column("users", "registration_status")
    op.drop_column("users", "email_verified")
