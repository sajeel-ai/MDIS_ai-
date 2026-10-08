"""Add hashed, expiring email verification codes."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_verification_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_auth_verification_codes_user_id", "auth_verification_codes", ["user_id"])
    op.create_index(
        "ix_auth_verification_user_purpose_created",
        "auth_verification_codes",
        ["user_id", "purpose", "created_at"],
    )
    op.create_index(
        "ix_auth_verification_active_expiry",
        "auth_verification_codes",
        ["user_id", "purpose", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_auth_verification_active_expiry", table_name="auth_verification_codes")
    op.drop_index("ix_auth_verification_user_purpose_created", table_name="auth_verification_codes")
    op.drop_index("ix_auth_verification_codes_user_id", table_name="auth_verification_codes")
    op.drop_table("auth_verification_codes")
