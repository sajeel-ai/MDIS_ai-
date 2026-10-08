"""006 — Create extractions and clinical_entities tables.

Revision ID: 006
Revises: 005
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "extractions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "processing_job_id",
            UUID(as_uuid=True),
            sa.ForeignKey("processing_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("model_name", sa.String(128), nullable=True),
        sa.Column("model_version", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_extractions_document_id", "extractions", ["document_id"])

    op.create_table(
        "clinical_entities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "extraction_id",
            UUID(as_uuid=True),
            sa.ForeignKey("extractions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("normalized_value", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="unreviewed"),
        sa.Column("details", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_clinical_entities_extraction_id", "clinical_entities", ["extraction_id"]
    )
    op.create_index(
        "ix_clinical_entities_entity_type", "clinical_entities", ["entity_type"]
    )
    op.create_index("ix_clinical_entities_status", "clinical_entities", ["status"])


def downgrade() -> None:
    op.drop_index("ix_clinical_entities_status", table_name="clinical_entities")
    op.drop_index("ix_clinical_entities_entity_type", table_name="clinical_entities")
    op.drop_index("ix_clinical_entities_extraction_id", table_name="clinical_entities")
    op.drop_table("clinical_entities")
    op.drop_index("ix_extractions_document_id", table_name="extractions")
    op.drop_table("extractions")
