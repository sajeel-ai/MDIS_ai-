"""013 keep user references immutable in audit rows."""

from alembic import op


revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("audit_events_user_id_fkey", "audit_events", type_="foreignkey")
    op.create_foreign_key(
        "fk_audit_events_user_id_users",
        "audit_events",
        "users",
        ["user_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_audit_events_user_id_users", "audit_events", type_="foreignkey")
    op.create_foreign_key(
        "audit_events_user_id_fkey",
        "audit_events",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )
