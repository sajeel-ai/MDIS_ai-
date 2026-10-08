"""014 prevent foreign-key actions from mutating append-only audit rows."""

from alembic import op


revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "fk_audit_events_organization_id_organizations", "audit_events", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_audit_events_organization_id_organizations",
        "audit_events",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_audit_events_organization_id_organizations", "audit_events", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_audit_events_organization_id_organizations",
        "audit_events",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="SET NULL",
    )
