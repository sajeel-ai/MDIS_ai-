"""Strict provider-independent contract for extracted clinical entities."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, ValidationError, ValidationInfo, field_validator, model_validator


class EntityType(str, Enum):
    DIAGNOSIS = "diagnosis"
    MEDICATION = "medication"
    SYMPTOM = "symptom"
    PROCEDURE = "procedure"
    LAB = "lab"


class CodeSystem(str, Enum):
    ICD10 = "ICD10"
    RXNORM = "RxNorm"
    SNOMED = "SNOMED"
    LOINC = "LOINC"
    CPT = "CPT"


class Assertion(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"
    POSSIBLE = "possible"
    HISTORICAL = "historical"
    FAMILY = "family"
    HYPOTHETICAL = "hypothetical"


class ExtractedEntity(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    type: EntityType
    raw_text: str = Field(min_length=1)
    normalized_value: str = Field(min_length=1)
    code: str | None
    code_system: CodeSystem | None
    confidence: float = Field(ge=0.0, le=1.0)
    assertion: Assertion
    section: str | None
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=0)
    evidence_text: str = Field(min_length=1)
    page_number: int = Field(ge=1)

    @field_validator("type", "code_system", "assertion", mode="before")
    @classmethod
    def parse_contract_enums(cls, value, info: ValidationInfo):
        # Pydantic's strict mode accepts enum instances only; JSON providers send
        # the enum's string value, so validate that exact value explicitly.
        enum_type = {"type": EntityType, "code_system": CodeSystem, "assertion": Assertion}[info.field_name]
        return value if value is None or isinstance(value, enum_type) else enum_type(value)

    @field_validator("raw_text", "normalized_value", "evidence_text")
    @classmethod
    def require_non_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must contain non-whitespace text")
        return value

    @model_validator(mode="after")
    def validate_offsets(self):
        if self.end_offset <= self.start_offset:
            raise ValueError("end_offset must be greater than start_offset")
        if (self.code is None) != (self.code_system is None):
            raise ValueError("code and code_system must be provided together")
        return self


def validate_entity_candidates(candidates: list) -> tuple[list[ExtractedEntity], list[dict]]:
    accepted = []
    rejected = []
    for index, candidate in enumerate(candidates):
        try:
            accepted.append(ExtractedEntity.model_validate(candidate))
        except ValidationError as error:
            rejected.append({"index": index, "reason": safe_validation_reason(error)})
        except (TypeError, ValueError):
            rejected.append({"index": index, "reason": "invalid_entity_shape"})
    return accepted, rejected


def verify_or_relocate_evidence(source_text: str, entity: ExtractedEntity) -> tuple[ExtractedEntity, bool]:
    if source_text[entity.start_offset:entity.end_offset] == entity.evidence_text:
        return entity, True
    relocated = source_text.find(entity.evidence_text)
    if relocated < 0:
        return entity, False
    return entity.model_copy(update={
        "start_offset": relocated,
        "end_offset": relocated + len(entity.evidence_text),
    }), True


def safe_validation_reason(error) -> str:
    """Summarize invalid fields without retaining rejected source values."""
    fields = sorted({".".join(str(part) for part in item["loc"]) for item in error.errors()})
    return "invalid_fields:" + ",".join(fields)
