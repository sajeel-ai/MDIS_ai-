"""012 tenant scoping, canonical roles, and append-only audit events."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None

DEFAULT_ORG_ID = "11111111-1111-4111-8111-111111111111"


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute(
        sa.text("INSERT INTO organizations (id, name) VALUES (CAST(:id AS uuid), :name)").bindparams(
            id=DEFAULT_ORG_ID, name="Default organization"
        )
    )

    for table in ("users", "patients", "documents"):
        op.add_column(
            table,
            sa.Column(
                "organization_id",
                UUID(as_uuid=True),
                nullable=True,
                server_default=sa.text(f"'{DEFAULT_ORG_ID}'::uuid"),
            ),
        )
        op.create_foreign_key(
            f"fk_{table}_organization_id_organizations",
            table,
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index(f"ix_{table}_organization_id", table, ["organization_id"])
        op.alter_column(table, "organization_id", nullable=False)

    op.execute("UPDATE users SET role = lower(role)")
    op.execute("UPDATE users SET role = 'operator' WHERE role = 'analyst'")
    op.execute(
        "UPDATE users SET role = 'viewer' "
        "WHERE role NOT IN ('admin', 'clinician', 'reviewer', 'viewer', 'operator')"
    )
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('admin', 'clinician', 'reviewer', 'viewer', 'operator')",
    )

    op.add_column(
        "audit_events",
        sa.Column(
            "organization_id", UUID(as_uuid=True), nullable=True,
            server_default=sa.text(f"'{DEFAULT_ORG_ID}'::uuid"),
        ),
    )
    op.execute(
        "UPDATE audit_events AS a SET organization_id = u.organization_id "
        "FROM users AS u WHERE a.user_id = u.id"
    )
    op.execute(
        "UPDATE audit_events SET metadata = jsonb_strip_nulls(jsonb_build_object(" 
        "'action', action, 'resource_id', resource_id, 'organization_id', organization_id))"
    )
    op.create_foreign_key(
        "fk_audit_events_organization_id_organizations",
        "audit_events",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_audit_events_organization_id", "audit_events", ["organization_id"])

    op.execute(
        """
        CREATE FUNCTION reject_audit_event_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER audit_events_append_only "
        "BEFORE UPDATE OR DELETE ON audit_events "
        "FOR EACH ROW EXECUTE FUNCTION reject_audit_event_mutation()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS reject_audit_event_mutation()")
    op.drop_index("ix_audit_events_organization_id", table_name="audit_events")
    op.drop_constraint("fk_audit_events_organization_id_organizations", "audit_events", type_="foreignkey")
    op.drop_column("audit_events", "organization_id")
    op.drop_constraint("ck_users_role", "users", type_="check")
    for table in ("documents", "patients", "users"):
        op.drop_index(f"ix_{table}_organization_id", table_name=table)
        op.drop_constraint(f"fk_{table}_organization_id_organizations", table, type_="foreignkey")
        op.drop_column(table, "organization_id")
    op.drop_table("organizations")
