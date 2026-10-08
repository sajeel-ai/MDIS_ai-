"""Review Center API schemas."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DocumentReviewSummary(BaseModel):
    id: str
    file_name: str
    document_type: str
    created_at: Optional[str] = None


class PatientReviewSummary(BaseModel):
    id: str
    display_name: str
    mrn: str


class EntityReviewSummary(BaseModel):
    id: str
    type: str
    raw_text: str
    normalized_value: Optional[str] = None
    confidence: float
    assertion: str = "present"
    section: Optional[str] = None
    status: str
    details: Optional[Dict[str, Any]] = None
    original_ai_value: Optional[str] = None


class EvidenceReviewSummary(BaseModel):
    id: Optional[str] = None
    text: str
    start_offset: int
    end_offset: int
    page_number: int


class ValidationReviewSummary(BaseModel):
    rule_code: Optional[str] = None
    severity: Optional[str] = None
    status: str
    message: Optional[str] = None


class ReviewTaskResponse(BaseModel):
    id: str
    document_id: str
    entity_id: Optional[str] = None
    priority: str
    reason: str
    status: str
    assigned_to: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    decision: Optional[str] = None
    comment: Optional[str] = None
    document: Optional[DocumentReviewSummary] = None
    patient: Optional[PatientReviewSummary] = None
    entity: Optional[EntityReviewSummary] = None
    evidence: Optional[EvidenceReviewSummary] = None
    validation: Optional[ValidationReviewSummary] = None
    validation_results: List[ValidationReviewSummary] = []
    source_text: Optional[str] = None


class ReviewDecisionRequest(BaseModel):
    decision: str = Field(..., description="approved | rejected | corrected")
    comment: Optional[str] = None
    corrected_value: Optional[str] = None
