"""Allow unavailable confidence for reviewer-added entities.

Revision ID: 029
Revises: 028
"""

from alembic import op
import sqlalchemy as sa

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "clinical_entities",
        "confidence",
        existing_type=sa.Numeric(5, 4),
        nullable=True,
    )


def downgrade() -> None:
    # Preserve rows written without a measured confidence: downgrade must not
    # invent a value. Refuse to make the column non-null while such rows exist.
    op.execute(
        """DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM clinical_entities WHERE confidence IS NULL) THEN
            RAISE EXCEPTION 'Cannot downgrade: clinical entities have unavailable confidence';
        END IF;
        END $$"""
    )
    op.alter_column(
        "clinical_entities",
        "confidence",
        existing_type=sa.Numeric(5, 4),
        nullable=False,
    )
