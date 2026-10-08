"""Index auth rate-limit windows for bounded cleanup."""

from alembic import op


revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_auth_rate_limit_window_started_at", "auth_rate_limit_buckets", ["window_started_at"])


def downgrade() -> None:
    op.drop_index("ix_auth_rate_limit_window_started_at", table_name="auth_rate_limit_buckets")
