"""002 — Create patients table.

Revision ID: 002
Revises: 001
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "patients",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("external_patient_id", sa.String(64), nullable=True),
        sa.Column("mrn", sa.String(32), nullable=True),
        sa.Column("first_name", sa.String(128), nullable=True),
        sa.Column("last_name", sa.String(128), nullable=True),
        sa.Column("dob", sa.Date(), nullable=True),
        sa.Column("gender", sa.String(16), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_patients_external_patient_id", "patients", ["external_patient_id"])
    op.create_index("ix_patients_mrn", "patients", ["mrn"])


def downgrade() -> None:
    op.drop_index("ix_patients_mrn", table_name="patients")
    op.drop_index("ix_patients_external_patient_id", table_name="patients")
    op.drop_table("patients")
