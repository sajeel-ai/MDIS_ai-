"""AIOps API schemas."""

from typing import List, Optional
from pydantic import BaseModel


class AIOpsMetricsResponse(BaseModel):
    total_jobs: int
    running_jobs: int
    failed_jobs: int
    completed_jobs: int
    avg_processing_ms: Optional[float] = None
    avg_confidence: Optional[float] = None
    avg_processing_sec: Optional[float] = None
    ocr_success_rate: Optional[float] = None
    extraction_accuracy: Optional[float] = None
    latest_eval: Optional[dict] = None


class AIOpsJobItem(BaseModel):
    job_id: str
    document_id: str
    case_id: str
    doc_type: str
    pipeline_version: str
    status: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    processing_ms: Optional[int] = None
    warning_count: int = 0
    step_count: int
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str


class AIOpsJobsResponse(BaseModel):
    jobs: List[AIOpsJobItem]


class AIOpsHealthResponse(BaseModel):
    status: str
    active_jobs: int
    avg_confidence: Optional[float] = None
    pipeline: str
