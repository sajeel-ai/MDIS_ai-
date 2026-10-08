"""Dashboard API schemas."""

from typing import Dict, List, Optional
from pydantic import BaseModel


class DashboardMetrics(BaseModel):
    total_documents: int
    processed: int
    pending_review: int
    failed: int
    success_rate: Optional[float] = None
    last_updated_at: str


class ReviewQueueSummary(BaseModel):
    high_priority: int
    medium_priority: int
    standard: int
    ai_conflicts: Optional[int] = None


class ExtractionQualityItem(BaseModel):
    entity_type: str
    model_confidence_uncalibrated: Optional[float] = None


class RecentCaseItem(BaseModel):
    id: str
    patient_name: Optional[str] = None
    mrn: Optional[str] = None
    doc_type: str
    status: str
    confidence: str
    review_status: str
    last_updated: str
    entity_counts: Dict[str, int]


class DashboardMetricsResponse(BaseModel):
    metrics: DashboardMetrics
    review_queue_summary: ReviewQueueSummary
    extraction_quality: List[ExtractionQualityItem]
    recent_cases: List[RecentCaseItem]
