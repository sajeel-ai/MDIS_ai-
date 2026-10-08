"""Add extraction rejection records, assertion context, and job warnings."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "extractions",
        sa.Column("rejected_entities", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "processing_jobs",
        sa.Column("warning_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "clinical_entities",
        sa.Column("assertion", sa.String(length=24), nullable=False, server_default="present"),
    )
    op.add_column("clinical_entities", sa.Column("section", sa.String(length=64), nullable=True))
    op.create_check_constraint(
        "ck_clinical_entities_assertion",
        "clinical_entities",
        "assertion IN ('present', 'absent', 'possible', 'historical', 'family', 'hypothetical')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_clinical_entities_assertion", "clinical_entities", type_="check")
    op.drop_column("clinical_entities", "section")
    op.drop_column("clinical_entities", "assertion")
    op.drop_column("processing_jobs", "warning_count")
    op.drop_column("extractions", "rejected_entities")
