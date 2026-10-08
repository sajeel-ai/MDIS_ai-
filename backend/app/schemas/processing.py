"""Processing Job API schemas."""

from typing import List, Optional
from pydantic import BaseModel
from app.workflows.states import ProcessingJobStatus, ProcessingStepStatus


class ProcessingStepResponse(BaseModel):
    id: str
    step_name: str
    status: ProcessingStepStatus
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    processing_ms: Optional[int] = None
    model_version: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class ProcessingJobResponse(BaseModel):
    job_id: str
    document_id: str
    status: ProcessingJobStatus
    pipeline_version: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    processing_ms: Optional[int] = None
    warning_count: int = 0
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    steps: List[ProcessingStepResponse] = []


class ProcessingJobStepsResponse(BaseModel):
    job_id: str
    steps: List[ProcessingStepResponse]
