"""Add document lifecycle query index to match model metadata.

Revision ID: 027
Revises: 026
"""
from alembic import op

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_documents_org_lifecycle_filters",
        "documents",
        ["organization_id", "status", "review_status", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_documents_org_lifecycle_filters", table_name="documents")
