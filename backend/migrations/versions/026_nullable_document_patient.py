"""Allow documents to remain searchable after patient unlinking.

Revision ID: 026
Revises: 025
"""
from alembic import op

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("documents_patient_id_fkey", "documents", type_="foreignkey")
    op.alter_column("documents", "patient_id", nullable=True)
    op.create_foreign_key(
        "documents_patient_id_fkey", "documents", "patients",
        ["patient_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    # Refuse downgrade when any document is unlinked rather than deleting it.
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM documents WHERE patient_id IS NULL) "
        "THEN RAISE EXCEPTION 'Cannot restore NOT NULL while unlinked documents exist'; "
        "END IF; END $$"
    )
    op.drop_constraint("documents_patient_id_fkey", "documents", type_="foreignkey")
    op.alter_column("documents", "patient_id", nullable=False)
    op.create_foreign_key(
        "documents_patient_id_fkey", "documents", "patients",
        ["patient_id"], ["id"], ondelete="CASCADE",
    )
