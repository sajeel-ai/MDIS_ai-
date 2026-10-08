"""Unit tests for OCR and Extraction Providers."""

import pytest
from app.providers.ocr import get_ocr_provider
from app.config import settings
from app.providers.extraction import (
    ExtractionProviderConfigurationError,
    get_extraction_provider,
    validate_extraction_provider_configuration,
)


@pytest.mark.asyncio
async def test_mock_ocr_provider():
    provider = get_ocr_provider("mock")
    res = await provider.extract_text(b"CLINICAL NOTE\nPatient presented with fever.")
    assert res["confidence"] is None
    assert "CLINICAL NOTE" in res["text"]
    assert res["engine"] == "mock_ocr"


@pytest.mark.asyncio
async def test_azure_ocr_missing_credentials_raises_error():
    provider = get_ocr_provider("azure")
    with pytest.raises(RuntimeError, match="AZURE_OCR_CONFIG_ERROR"):
        await provider.extract_text(b"TEST NOTE", mime_type="text/plain")


@pytest.mark.asyncio
async def test_azure_ocr_returns_provider_text_and_word_confidence(monkeypatch):
    import httpx
    from app.providers.ocr.azure import AzureOCRProvider

    class FakeResponse:
        headers = {"Operation-Location": "https://azure.example.test/operations/1"}

        def __init__(self, data):
            self.data = data

        def raise_for_status(self):
            return None

        def json(self):
            return self.data

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return FakeResponse({"status": "running"})

        async def get(self, *args, **kwargs):
            return FakeResponse({
                "status": "succeeded",
                "analyzeResult": {
                    "content": "Synthetic diagnosis",
                    "pages": [{
                        "pageNumber": 1,
                        "lines": [{"content": "Synthetic diagnosis"}],
                        "words": [{"confidence": 0.8}, {"confidence": 1.0}],
                    }],
                },
            })

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr("app.providers.ocr.azure.asyncio.sleep", lambda *_: _no_wait())
    result = await AzureOCRProvider("https://azure.example.test", "synthetic-key").extract_text(b"synthetic")
    assert result["text"] == "Synthetic diagnosis"
    assert result["confidence"] == pytest.approx(0.9)
    assert result["page_count"] == 1


async def _no_wait():
    return None


@pytest.mark.asyncio
async def test_azure_ocr_rejects_foreign_operation_url_without_polling(monkeypatch):
    import httpx
    from app.providers.ocr.azure import AzureOCRProvider

    class FakeResponse:
        headers = {"Operation-Location": "https://attacker.example.test/steal"}

        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "running"}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return FakeResponse()

        async def get(self, *args, **kwargs):
            pytest.fail("Must not send provider credentials to a foreign host")

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    with pytest.raises(RuntimeError, match="OCR_FAILED"):
        await AzureOCRProvider("https://azure.example.test", "synthetic-key").extract_text(b"synthetic")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"status": "failed"},
        {"status": "succeeded", "analyzeResult": {"content": "  "}},
    ],
)
async def test_azure_ocr_fails_closed_on_provider_failure_or_empty_text(monkeypatch, payload):
    import httpx
    from app.providers.ocr.azure import AzureOCRProvider

    class FakeResponse:
        headers = {}

        def raise_for_status(self):
            return None

        def json(self):
            return payload

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    with pytest.raises(RuntimeError, match="OCR_FAILED"):
        await AzureOCRProvider("https://azure.example.test", "synthetic-key").extract_text(b"synthetic")


def test_openai_provider_valid_configuration(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key-not-a-secret")
    monkeypatch.setattr(settings, "openai_model", "test-model")
    provider = get_extraction_provider("openai")
    assert provider.api_key == "test-key-not-a-secret"
    assert provider.model == "test-model"


def test_local_provider_valid_configuration():
    assert validate_extraction_provider_configuration("local") == "local"


def test_openai_provider_missing_key_is_rejected():
    with pytest.raises(ExtractionProviderConfigurationError, match="OPENAI_API_KEY"):
        validate_extraction_provider_configuration("openai", api_key="  ")


def test_invalid_provider_configuration_is_rejected():
    with pytest.raises(ExtractionProviderConfigurationError, match="Unsupported extraction provider"):
        validate_extraction_provider_configuration("unconfigured-provider")


def test_openai_provider_missing_model_is_rejected():
    with pytest.raises(ExtractionProviderConfigurationError, match="OPENAI_MODEL"):
        validate_extraction_provider_configuration(
            "openai", api_key="test-key-not-a-secret", model=" "
        )


@pytest.mark.asyncio
async def test_openai_provider_errors_do_not_expose_api_key(monkeypatch, caplog):
    import httpx
    from app.providers.extraction.openai import OpenAIExtractionProvider

    secret = "sk-test-secret-value"

    class FakeResponse:
        def raise_for_status(self):
            raise RuntimeError(f"provider echoed {secret}")

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    provider = OpenAIExtractionProvider(api_key=secret, model="test-model")

    with pytest.raises(RuntimeError) as exc_info:
        await provider.extract_clinical_entities("test text")

    assert secret not in str(exc_info.value)
    assert secret not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("choice", "expected_code"),
    [
        ({"finish_reason": "length", "message": {"content": "{}"}}, "EXTRACTION_TRUNCATED"),
        ({"finish_reason": "stop", "message": {"refusal": "not permitted", "content": None}}, "EXTRACTION_REFUSED"),
        ({"finish_reason": "stop", "message": {"content": "not-json"}}, "EXTRACTION_SCHEMA_ERROR"),
    ],
)
async def test_openai_structured_output_failures_are_typed(monkeypatch, choice, expected_code):
    import httpx
    from app.providers.extraction.openai import OpenAIExtractionProvider
    from app.providers.extraction.base import ExtractionProviderFailure

    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [choice]}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            captured.update(kwargs)
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    provider = OpenAIExtractionProvider(api_key="test-key", model="test-model")
    with pytest.raises(ExtractionProviderFailure) as exc_info:
        await provider.extract_clinical_entities("synthetic text")

    assert exc_info.value.code == expected_code
    schema_format = captured["json"]["response_format"]
    assert schema_format["type"] == "json_schema"
    assert schema_format["json_schema"]["strict"] is True
    assert captured["json"]["temperature"] < 0.2


@pytest.mark.asyncio
async def test_openai_successful_response_is_validated_by_entity_contract(monkeypatch):
    import httpx
    from app.providers.extraction.openai import OpenAIExtractionProvider
    from app.schemas.entity_contract import validate_entity_candidates

    content = {
        "entities": [{
            "type": "diagnosis", "raw_text": "pneumonia", "normalized_value": "Pneumonia",
            "code": "J18.9", "code_system": "ICD10", "confidence": 0.72,
            "assertion": "possible", "section": None, "start_offset": 10,
            "end_offset": 19, "evidence_text": "pneumonia", "page_number": 1,
        }]
    }

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            import json
            return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(content)}}]}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    result = await OpenAIExtractionProvider(api_key="test-key", model="test-model").extract_clinical_entities("synthetic pneumonia")
    accepted, rejected = validate_entity_candidates(result["entities"])
    assert len(accepted) == 1
    assert rejected == []
