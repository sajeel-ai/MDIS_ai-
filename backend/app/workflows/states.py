"""Canonical clinical document, review, and processing state vocabularies."""

from typing import Iterable, Literal

DocumentStatus = Literal["uploaded", "queued", "processing", "completed", "failed"]
ReviewStatus = Literal["not_required", "pending", "in_review", "approved", "rejected"]
LifecycleStatus = Literal["uploaded", "processing", "failed", "extracted", "in_review", "approved", "rejected"]
ProcessingStepStatus = Literal["pending", "running", "completed", "failed", "skipped"]
ProcessingJobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]

DOCUMENT_STATUSES = ("uploaded", "queued", "processing", "completed", "failed")
REVIEW_STATUSES = ("not_required", "pending", "in_review", "approved", "rejected")
PROCESSING_STEP_STATUSES = ("pending", "running", "completed", "failed", "skipped")
PROCESSING_JOB_STATUSES = ("queued", "running", "completed", "failed", "cancelled")


def derive_lifecycle_status(document_status: str, review_status: str) -> LifecycleStatus:
    """Collapse processing and review state into one user-facing status.

    Processing always wins over review state so stale approval values cannot make
    a queued, running, or failed document appear approved.
    """
    if document_status == "failed":
        return "failed"
    if document_status == "processing":
        return "processing"
    if document_status in {"uploaded", "queued"}:
        return "uploaded"
    if review_status == "rejected":
        return "rejected"
    if review_status == "approved":
        return "approved"
    if review_status in {"pending", "in_review"}:
        return "in_review"
    return "extracted"


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
