"""003 — Create encounters and icd_codes tables.

Revision ID: 003
Revises: 002
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "encounters",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "patient_id",
            UUID(as_uuid=True),
            sa.ForeignKey("patients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_encounter_id", sa.String(64), nullable=True),
        sa.Column("admit_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discharge_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("los_hours", sa.Numeric(8, 2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_encounters_patient_id", "encounters", ["patient_id"])
    op.create_index(
        "ix_encounters_external_encounter_id", "encounters", ["external_encounter_id"]
    )

    op.create_table(
        "icd_codes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "encounter_id",
            UUID(as_uuid=True),
            sa.ForeignKey("encounters.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("code_type", sa.String(8), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_icd_codes_encounter_id", "icd_codes", ["encounter_id"])
    op.create_index("ix_icd_codes_code", "icd_codes", ["code"])


def downgrade() -> None:
    op.drop_index("ix_icd_codes_code", table_name="icd_codes")
    op.drop_index("ix_icd_codes_encounter_id", table_name="icd_codes")
    op.drop_table("icd_codes")
    op.drop_index("ix_encounters_external_encounter_id", table_name="encounters")
    op.drop_index("ix_encounters_patient_id", table_name="encounters")
    op.drop_table("encounters")
