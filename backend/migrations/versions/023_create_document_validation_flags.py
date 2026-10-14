"""023 — Create document_validation_flags table.

Revision ID: 023
Revises: 022
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_validation_flags",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "extraction_id",
            UUID(as_uuid=True),
            sa.ForeignKey("extractions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rule_code", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("details", JSONB, nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_dvf_document_id", "document_validation_flags", ["document_id"]
    )
    op.create_index(
        "ix_dvf_extraction_id", "document_validation_flags", ["extraction_id"]
    )
    op.create_index(
        "ix_dvf_rule_code", "document_validation_flags", ["rule_code"]
    )
    op.execute(
        "CREATE INDEX ix_dvf_active ON document_validation_flags (document_id) "
        "WHERE superseded_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_dvf_active")
    op.drop_index("ix_dvf_rule_code", table_name="document_validation_flags")
    op.drop_index("ix_dvf_extraction_id", table_name="document_validation_flags")
    op.drop_index("ix_dvf_document_id", table_name="document_validation_flags")
    op.drop_table("document_validation_flags")
