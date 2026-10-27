"""Clinical Document Annotation Schema.

Defines the data contract for annotated reference documents used to evaluate
OCR quality, clinical information extraction, and layout alignment.
"""

from typing import Any, List, Optional
from pydantic import BaseModel, Field


class Span(BaseModel):
    start_offset: int = Field(..., ge=0, description="Start character offset in text")
    end_offset: int = Field(..., ge=0, description="End character offset in text")


class AnnotatedEntity(BaseModel):
    type: str = Field(..., description="Entity type (e.g. diagnosis, medication, symptom, procedure, lab)")
    text: Optional[str] = Field(None, description="Exact raw text span in the document")
    normalized_value: str = Field(..., description="Normalized clinical concept name or terminology mapping")
    span: Optional[Span] = Field(None, description="Character offsets [start_offset, end_offset]")
    negated: bool = Field(False, description="True if the entity is clinically negated/absent")
    temporality: str = Field(
        "current",
        description="Temporality / assertion state: current | historical | hypothetical | possible | family",
    )
    assertion: str = Field(
        "present",
        description="Assertion value matching MDIS schema: present | absent | possible | historical | hypothetical | family",
    )
    bounding_box: Optional[List[float]] = Field(
        None,
        description="Normalized or pixel bounding box [x_min, y_min, x_max, y_max]",
    )
    code: Optional[str] = Field(None, description="Clinical code (ICD-10, RxNorm, SNOMED, LOINC)")
    code_system: Optional[str] = Field(None, description="Coding system name")


class AnnotatedDocument(BaseModel):
    id: str = Field(..., description="Unique document fixture identifier (e.g. DOC-001)")
    category: str = Field(
        "unspecified",
        description="Document category: discharge_summary | progress_note | emergency_note | radiology_report | lab_report",
    )
    ground_truth_text: str = Field(..., description="Gold-standard verified text transcribed from clinical record")
    ocr_text: Optional[str] = Field(None, description="OCR-extracted text (used to calculate CER and WER)")
    entities: List[AnnotatedEntity] = Field(default_factory=list, description="List of annotated clinical entities")
    metadata: Optional[dict[str, Any]] = Field(default_factory=dict, description="Metadata such as patient MRN, source format, etc.")

