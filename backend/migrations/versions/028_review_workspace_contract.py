"""Add nullable review contract metadata, revisions, concurrency, and soft deletion.

Revision ID: 028
Revises: 027
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("patients", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("document_versions", sa.Column("ocr_pages", postgresql.JSONB(), nullable=True))
    op.add_column("evidence_spans", sa.Column("bbox", postgresql.JSONB(), nullable=True))
    op.add_column("clinical_entities", sa.Column("experiencer", sa.String(16), nullable=True))
    op.add_column("clinical_entities", sa.Column("temporality", sa.String(16), nullable=True))
    op.add_column("clinical_entities", sa.Column("exclusion_reason", sa.Text(), nullable=True))
    op.add_column("clinical_entities", sa.Column("ocr_confidence", sa.Numeric(5, 4), nullable=True))
    op.add_column("clinical_entities", sa.Column("source", sa.String(24), nullable=True))
    op.add_column("clinical_entities", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("review_tasks", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.create_table(
        "clinical_entity_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinical_entities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source", sa.String(24), nullable=False),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("before", postgresql.JSONB(), nullable=True),
        sa.Column("after", postgresql.JSONB(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_clinical_entity_revisions_entity_id", "clinical_entity_revisions", ["entity_id"])
    op.create_index("ix_clinical_entity_revisions_actor_user_id", "clinical_entity_revisions", ["actor_user_id"])


def downgrade() -> None:
    op.drop_index("ix_clinical_entity_revisions_actor_user_id", table_name="clinical_entity_revisions")
    op.drop_index("ix_clinical_entity_revisions_entity_id", table_name="clinical_entity_revisions")
    op.drop_table("clinical_entity_revisions")
    op.drop_column("review_tasks", "version")
    op.drop_column("clinical_entities", "version")
    op.drop_column("clinical_entities", "ocr_confidence")
    op.drop_column("clinical_entities", "source")
    op.drop_column("clinical_entities", "exclusion_reason")
    op.drop_column("clinical_entities", "temporality")
    op.drop_column("clinical_entities", "experiencer")
    op.drop_column("evidence_spans", "bbox")
    op.drop_column("document_versions", "ocr_pages")
    op.drop_column("patients", "deleted_at")
