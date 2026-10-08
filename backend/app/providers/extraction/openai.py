"""OpenAI structured-output clinical entity extraction provider."""

import logging
import json

from pydantic import ValidationError

from app.config import settings
from app.providers.extraction.base import (
    BaseExtractionProvider,
    ExtractionProviderFailure,
    ExtractionResult,
)
from app.schemas.entity_contract import ExtractedEntity

logger = logging.getLogger(__name__)

ENTITY_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "type": {"type": "string", "enum": ["diagnosis", "medication", "symptom", "procedure", "lab"]},
        "raw_text": {"type": "string"},
        "normalized_value": {"type": "string"},
        "code": {"type": ["string", "null"]},
        "code_system": {"type": ["string", "null"], "enum": ["ICD10", "RxNorm", "SNOMED", "LOINC", "CPT", None]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "assertion": {"type": "string", "enum": ["present", "absent", "possible", "historical", "family", "hypothetical"]},
        "section": {"type": ["string", "null"]},
        "start_offset": {"type": "integer", "minimum": 0},
        "end_offset": {"type": "integer", "minimum": 1},
        "evidence_text": {"type": "string"},
        "page_number": {"type": "integer", "minimum": 1},
    },
    "required": [
        "type", "raw_text", "normalized_value", "code", "code_system", "confidence",
        "assertion", "section", "start_offset", "end_offset", "evidence_text", "page_number",
    ],
}

EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"entities": {"type": "array", "items": ENTITY_JSON_SCHEMA}},
    "required": ["entities"],
}

EXTRACTION_SYSTEM_PROMPT = """Extract diagnoses, medications, symptoms, procedures, and lab findings from the supplied clinical text.
Return each entity's raw_text and evidence_text verbatim as a contiguous source substring. start_offset/end_offset must point to evidence_text using zero-based, end-exclusive character offsets. Use the assertion that matches the stated context; do not infer unsupported facts. If no entities are present, return an empty entities array."""


class OpenAIExtractionProvider(BaseExtractionProvider):
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = (settings.openai_api_key if api_key is None else api_key).strip()
        self.model = (settings.openai_model if model is None else model).strip()

    async def extract_clinical_entities(self, text: str) -> ExtractionResult:
        if not self.api_key:
            raise ExtractionProviderFailure("PROVIDER_CONFIGURATION_ERROR", "OpenAI key is not configured")
        try:
            import httpx

            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            payload = {
                "model": self.model,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "clinical_entities", "strict": True, "schema": EXTRACTION_SCHEMA},
                },
                "messages": [
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                "temperature": 0.1,
            }
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()
            choice = data["choices"][0]
            message = choice["message"]
            if message.get("refusal"):
                raise ExtractionProviderFailure("EXTRACTION_REFUSED", "Provider refused the extraction request")
            if choice.get("finish_reason") == "length":
                raise ExtractionProviderFailure("EXTRACTION_TRUNCATED", "Provider response was truncated")
            content = message.get("content")
            if not isinstance(content, str) or not content:
                raise ExtractionProviderFailure("EXTRACTION_SCHEMA_ERROR", "Provider returned no structured content")
            parsed = json.loads(content)
            if not isinstance(parsed, dict) or set(parsed) != {"entities"} or not isinstance(parsed["entities"], list):
                raise ExtractionProviderFailure("EXTRACTION_SCHEMA_ERROR", "Provider response did not match the required schema")
            entities = [ExtractedEntity.model_validate(item).model_dump(mode="json") for item in parsed["entities"]]
            return ExtractionResult(
                entities=entities,
                model_name="openai",
                model_version=self.model,
                raw_response={"status": "success", "entity_count": len(entities)},
            )
        except ExtractionProviderFailure:
            raise
        except ValidationError:
            logger.warning("OpenAI extraction schema validation failed")
            raise ExtractionProviderFailure("EXTRACTION_SCHEMA_ERROR", "Provider response failed schema validation") from None
        except json.JSONDecodeError:
            logger.warning("OpenAI extraction returned invalid structured JSON")
            raise ExtractionProviderFailure("EXTRACTION_SCHEMA_ERROR", "Provider response was not valid structured JSON") from None
        except (KeyError, IndexError, TypeError):
            logger.warning("OpenAI extraction returned an incomplete response envelope")
            raise ExtractionProviderFailure("EXTRACTION_SCHEMA_ERROR", "Provider response was incomplete") from None
        except Exception as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            error_type = type(exc).__name__
            logger.error("OpenAI extraction request failed error_type=%s status_code=%s", error_type, status_code)
            raise ExtractionProviderFailure("EXTRACTION_FAILED", "OpenAI request or response failed") from None
