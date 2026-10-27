"""Allow audit events to enter legal hold without editing their content."""

from alembic import op


revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_audit_event_mutation() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'UPDATE'
               AND OLD.legal_hold IS FALSE
               AND NEW.legal_hold IS TRUE
               AND (to_jsonb(NEW) - 'legal_hold') = (to_jsonb(OLD) - 'legal_hold') THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'audit_events is append-only except for setting legal_hold';
        END;
        $$ LANGUAGE plpgsql
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_audit_event_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
