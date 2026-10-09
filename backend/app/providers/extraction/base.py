"""LLM Clinical Extraction Provider Base Interface."""

from abc import ABC, abstractmethod
from typing import TypedDict, List, Dict, Any


class ExtractionProviderFailure(RuntimeError):
    """Typed extraction failure with a safe code and no source text in its message."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


class ExtractedEntityData(TypedDict):
    type: str  # diagnosis, medication, symptom, procedure, lab
    raw_text: str
    normalized_value: str
    code: str
    code_system: str
    confidence: float
    evidence_text: str
    start_offset: int
    end_offset: int
    page_number: int
    # Structured attributes such as medication dose/frequency and lab units.
    details: Dict[str, Any]


class ExtractionResult(TypedDict):
    entities: List[ExtractedEntityData]
    model_name: str
    model_version: str
    raw_response: Dict[str, Any]


class BaseExtractionProvider(ABC):
    @abstractmethod
    async def extract_clinical_entities(self, text: str) -> ExtractionResult:
        """Extract structured clinical entities and evidence from source text."""
        pass
