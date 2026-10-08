"""010 — Separate processing and review states; formalize step errors.

Revision ID: 010
Revises: 009
"""

from alembic import op
import sqlalchemy as sa

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "review_status",
            sa.String(length=32),
            nullable=False,
            server_default="not_required",
        ),
    )
    op.create_index("ix_documents_review_status", "documents", ["review_status"])
    op.add_column("processing_steps", sa.Column("error_code", sa.String(length=64), nullable=True))

    op.execute(
        """
        UPDATE documents AS d
        SET review_status = CASE
            WHEN d.status = 'in_review' OR EXISTS (
                SELECT 1 FROM review_tasks AS r
                WHERE r.document_id = d.id AND r.status = 'in_review'
            ) THEN 'in_review'
            WHEN EXISTS (
                SELECT 1 FROM review_tasks AS r
                WHERE r.document_id = d.id AND r.status = 'pending'
            ) THEN 'pending'
            WHEN EXISTS (
                SELECT 1 FROM review_tasks AS r
                WHERE r.document_id = d.id AND r.status IN ('rejected', 'needs_correction')
            ) THEN 'rejected'
            WHEN EXISTS (
                SELECT 1 FROM review_tasks AS r
                WHERE r.document_id = d.id AND r.status IN ('approved', 'corrected')
            ) THEN 'approved'
            ELSE 'not_required'
        END
        """
    )
    op.execute(
        """
        UPDATE processing_steps AS s
        SET status = 'failed',
            completed_at = COALESCE(s.completed_at, now()),
            error_code = COALESCE(s.error_code, j.error_code, 'PROCESSING_ERROR'),
            error_message = COALESCE(
                s.error_message,
                j.error_message,
                'Step was still running when its processing job had already failed.'
            )
        FROM processing_jobs AS j
        WHERE s.processing_job_id = j.id
          AND s.status = 'running'
          AND j.status = 'failed'
        """
    )
    op.execute(
        """
        UPDATE documents
        SET status = CASE
            WHEN status = 'pending' THEN 'uploaded'
            WHEN status IN ('ocr_processing', 'extracting', 'validating') THEN 'processing'
            WHEN status = 'in_review' THEN 'completed'
            WHEN status IN ('uploaded', 'queued', 'processing', 'completed', 'failed') THEN status
            ELSE 'uploaded'
        END
        """
    )

    op.alter_column("documents", "status", server_default="uploaded")
    op.create_check_constraint(
        "ck_documents_processing_status",
        "documents",
        "status IN ('uploaded', 'queued', 'processing', 'completed', 'failed')",
    )
    op.create_check_constraint(
        "ck_documents_review_status",
        "documents",
        "review_status IN ('not_required', 'pending', 'in_review', 'approved', 'rejected')",
    )
    op.create_check_constraint(
        "ck_processing_jobs_status",
        "processing_jobs",
        "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
    )
    op.create_check_constraint(
        "ck_processing_steps_status",
        "processing_steps",
        "status IN ('pending', 'running', 'completed', 'failed', 'skipped')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_processing_steps_status", "processing_steps", type_="check")
    op.drop_constraint("ck_processing_jobs_status", "processing_jobs", type_="check")
    op.drop_constraint("ck_documents_review_status", "documents", type_="check")
    op.drop_constraint("ck_documents_processing_status", "documents", type_="check")
    op.execute(
        """
        UPDATE documents
        SET status = CASE
            WHEN status = 'uploaded' THEN 'pending'
            WHEN status = 'processing' THEN 'ocr_processing'
            WHEN status = 'completed' AND review_status = 'in_review' THEN 'in_review'
            ELSE status
        END
        """
    )
    op.alter_column("documents", "status", server_default="queued")
    op.drop_column("processing_steps", "error_code")
    op.drop_index("ix_documents_review_status", table_name="documents")
    op.drop_column("documents", "review_status")
