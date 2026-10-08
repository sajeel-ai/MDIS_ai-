"""Persist validation rule codes and original AI values."""

from alembic import op
import sqlalchemy as sa

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("validation_results", sa.Column("rule_code", sa.String(length=64), nullable=True))
    op.execute("UPDATE validation_results SET rule_code = upper(validation_rule) WHERE rule_code IS NULL")
    op.create_index("ix_validation_results_rule_code", "validation_results", ["rule_code"])
    op.add_column("clinical_entities", sa.Column("original_ai_value", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("clinical_entities", "original_ai_value")
    op.drop_index("ix_validation_results_rule_code", table_name="validation_results")
    op.drop_column("validation_results", "rule_code")
