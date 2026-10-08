"""Canonical clinical document, review, and processing state vocabularies."""

from typing import Iterable, Literal

DocumentStatus = Literal["uploaded", "queued", "processing", "completed", "failed"]
ReviewStatus = Literal["not_required", "pending", "in_review", "approved", "rejected"]
ProcessingStepStatus = Literal["pending", "running", "completed", "failed", "skipped"]
ProcessingJobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]

DOCUMENT_STATUSES = ("uploaded", "queued", "processing", "completed", "failed")
REVIEW_STATUSES = ("not_required", "pending", "in_review", "approved", "rejected")
PROCESSING_STEP_STATUSES = ("pending", "running", "completed", "failed", "skipped")
PROCESSING_JOB_STATUSES = ("queued", "running", "completed", "failed", "cancelled")


def aggregate_review_status(task_statuses: Iterable[str]) -> ReviewStatus:
    statuses = tuple(task_statuses)
    if not statuses:
        return "not_required"
    if "in_review" in statuses:
        return "in_review"
    if "pending" in statuses:
        return "pending"
    if "rejected" in statuses or "needs_correction" in statuses:
        return "rejected"
    return "approved"
