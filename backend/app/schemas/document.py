"""Document API schemas."""

from typing import List, Literal, Optional
from pydantic import BaseModel
from app.workflows.states import DocumentStatus, LifecycleStatus, ReviewStatus


class PipelineStage(BaseModel):
    name: str
    status: str
    detail: str
    throughput: str


class DocumentResponse(BaseModel):
    id: str
    case_id: str
    file_name: Optional[str] = None
    patient_name: Optional[str] = None
    mrn: Optional[str] = None
    doc_type: str
    status: DocumentStatus
    review_status: ReviewStatus = "not_required"
    lifecycle_status: LifecycleStatus = "extracted"
    confidence: str
    last_updated: str


class DocumentDetailResponse(DocumentResponse):
    dob: Optional[str] = None
    source_text: str
    version_number: int
    page_count: int
    file_name: str
    mime_type: str
    size_bytes: int
    pipeline_stages: List[PipelineStage]


class DocumentProcessResponse(BaseModel):
    job_id: str
    document_id: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    message: str
