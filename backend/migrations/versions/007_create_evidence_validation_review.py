"""007 — Create evidence_spans, validation_results, and review_tasks tables.

Revision ID: 007
Revises: 006
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # evidence_spans — character-level link from entity to document version text
    op.create_table(
        "evidence_spans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "entity_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clinical_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_version_id",
            UUID(as_uuid=True),
            sa.ForeignKey("document_versions.id"),
            nullable=False,
        ),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_evidence_spans_entity_id", "evidence_spans", ["entity_id"])
    op.create_index(
        "ix_evidence_spans_document_version_id",
        "evidence_spans",
        ["document_version_id"],
    )

    # validation_results — per-rule outcomes per entity
    op.create_table(
        "validation_results",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "entity_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clinical_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("validation_rule", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("severity", sa.String(16), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_validation_results_entity_id", "validation_results", ["entity_id"]
    )

    # review_tasks — human review queue items
    op.create_table(
        "review_tasks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "entity_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clinical_entities.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("priority", sa.String(16), nullable=False, server_default="normal"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column(
            "assigned_to",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision", sa.String(32), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
    )
    op.create_index("ix_review_tasks_status", "review_tasks", ["status"])
    op.create_index("ix_review_tasks_priority", "review_tasks", ["priority"])
    op.create_index("ix_review_tasks_entity_id", "review_tasks", ["entity_id"])
    op.create_index("ix_review_tasks_document_id", "review_tasks", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_review_tasks_document_id", table_name="review_tasks")
    op.drop_index("ix_review_tasks_entity_id", table_name="review_tasks")
    op.drop_index("ix_review_tasks_priority", table_name="review_tasks")
    op.drop_index("ix_review_tasks_status", table_name="review_tasks")
    op.drop_table("review_tasks")
    op.drop_index("ix_validation_results_entity_id", table_name="validation_results")
    op.drop_table("validation_results")
    op.drop_index(
        "ix_evidence_spans_document_version_id", table_name="evidence_spans"
    )
    op.drop_index("ix_evidence_spans_entity_id", table_name="evidence_spans")
    op.drop_table("evidence_spans")
