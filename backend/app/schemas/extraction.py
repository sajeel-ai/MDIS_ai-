"""Extraction, Entity, and Evidence API schemas."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class EvidenceSpanResponse(BaseModel):
    id: str
    entity_id: str
    start_offset: int
    end_offset: int
    exact_text: str
    sentence_text: Optional[str] = None
    section_name: Optional[str] = None


class ClinicalEntityResponse(BaseModel):
    id: str
    extraction_id: str
    entity_type: str
    raw_text: str
    normalized_value: Optional[str] = None
    confidence: float
    assertion: str = "present"
    section: Optional[str] = None
    status: str
    details: Optional[Dict[str, Any]] = None
    validation_rule_codes: List[str] = []
    evidence_spans: List[EvidenceSpanResponse] = []


class ExtractionResponse(BaseModel):
    id: str
    document_id: str
    processing_job_id: Optional[str] = None
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    status: str
    created_at: str
    entities: List[ClinicalEntityResponse] = []
