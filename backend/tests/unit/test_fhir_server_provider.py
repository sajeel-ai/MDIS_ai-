"""Network-free tests for FHIR metadata and transaction request construction."""

import httpx
import pytest

from app.providers import fhir_server
from app.providers.fhir_server import ConfiguredFHIRServerProvider


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self.payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://fhir.test")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("failed", request=request, response=response)

    def json(self):
        return self.payload


@pytest.mark.asyncio
async def test_metadata_uses_real_fhir_metadata_endpoint(monkeypatch):
    calls = []

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url):
            calls.append(url)
            return FakeResponse(200, {"resourceType": "CapabilityStatement", "fhirVersion": "4.0.1"})

    monkeypatch.setattr(fhir_server.httpx, "AsyncClient", lambda **kwargs: Client())
    result = await ConfiguredFHIRServerProvider("https://fhir.test", max_attempts=1, backoff_seconds=0).get_metadata()
    assert calls == ["https://fhir.test/metadata"]
    assert result["fhirVersion"] == "4.0.1"


@pytest.mark.asyncio
async def test_push_uses_conditional_create_and_retries_without_logging_payload(monkeypatch):
    calls = []

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, *, json, headers):
            calls.append(json)
            return FakeResponse(500 if len(calls) == 1 else 200)

    async def no_wait(_seconds):
        return None

    monkeypatch.setattr(fhir_server.httpx, "AsyncClient", lambda **kwargs: Client())
    monkeypatch.setattr(fhir_server.asyncio, "sleep", no_wait)
    result = await ConfiguredFHIRServerProvider("https://fhir.test", max_attempts=2, backoff_seconds=0).push_transaction({
        "resourceType": "Bundle", "type": "document",
        "entry": [{"fullUrl": "urn:uuid:00000000-0000-0000-0000-000000000001", "resource": {"resourceType": "Patient", "id": "00000000-0000-0000-0000-000000000001"}}],
    })
    assert result["attempts"] == 2
    assert calls[0]["type"] == "transaction"
    assert calls[0]["entry"][0]["request"] == {
        "method": "POST", "url": "Patient", "ifNoneExist": "_id=00000000-0000-0000-0000-000000000001",
    }
