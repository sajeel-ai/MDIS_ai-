"""Enforce one active processing job per document.

Revision ID: 011
Revises: 010
"""

from alembic import op
import sqlalchemy as sa


revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Preserve the currently running job where possible; cancel redundant
    # active rows before installing the uniqueness guard.
    op.execute(
        sa.text(
            """
            WITH ranked_active_jobs AS (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY document_id
                           ORDER BY CASE WHEN status = 'running' THEN 0 ELSE 1 END,
                                    created_at ASC,
                                    id ASC
                       ) AS position
                FROM processing_jobs
                WHERE status IN ('queued', 'running')
            )
            UPDATE processing_jobs AS job
            SET status = 'cancelled',
                completed_at = COALESCE(job.completed_at, now()),
                error_code = COALESCE(job.error_code, 'DUPLICATE_ACTIVE_JOB'),
                error_message = COALESCE(
                    job.error_message,
                    'Cancelled during migration because another active job exists for this document.'
                )
            FROM ranked_active_jobs AS ranked
            WHERE job.id = ranked.id
              AND ranked.position > 1
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE processing_steps AS step
            SET status = 'failed',
                completed_at = COALESCE(step.completed_at, now()),
                error_code = COALESCE(step.error_code, 'DUPLICATE_ACTIVE_JOB'),
                error_message = COALESCE(
                    step.error_message,
                    'Step was interrupted when a duplicate active job was cancelled during migration.'
                )
            FROM processing_jobs AS job
            WHERE step.processing_job_id = job.id
              AND job.error_code = 'DUPLICATE_ACTIVE_JOB'
              AND step.status = 'running'
            """
        )
    )
    op.create_index(
        "uq_processing_jobs_one_active_per_document",
        "processing_jobs",
        ["document_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
        sqlite_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_processing_jobs_one_active_per_document",
        table_name="processing_jobs",
    )
