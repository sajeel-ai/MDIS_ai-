"""Outbound FHIR test-server provider. Request bodies are never logged."""

import asyncio
import logging
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class FHIRServerProvider(Protocol):
    async def get_metadata(self) -> dict[str, Any]: ...
    async def push_transaction(self, bundle: dict[str, Any]) -> dict[str, Any]: ...


class ConfiguredFHIRServerProvider:
    def __init__(self, base_url: str, *, max_attempts: int, backoff_seconds: float):
        self.base_url = base_url.rstrip("/")
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds

    async def get_metadata(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{self.base_url}/metadata")
        response.raise_for_status()
        return response.json()

    async def push_transaction(self, bundle: dict[str, Any]) -> dict[str, Any]:
        transaction = {**bundle, "type": "transaction"}
        for entry in transaction.get("entry", []):
            resource = entry.get("resource", {})
            resource_type, resource_id = resource.get("resourceType"), resource.get("id")
            if not resource_type or not resource_id:
                raise ValueError("FHIR transaction entry requires a resource type and ID")
            entry["request"] = {"method": "POST", "url": resource_type, "ifNoneExist": f"_id={resource_id}"}

        parsed = urlparse(self.base_url)
        safe_host = parsed.hostname or "configured test server"
        for attempt in range(1, self.max_attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.post(self.base_url, json=transaction, headers={"Content-Type": "application/fhir+json"})
                response.raise_for_status()
                logger.info("FHIR transaction completed host=%s attempt=%d status=%d", safe_host, attempt, response.status_code)
                return {"status": "completed", "attempts": attempt, "http_status": response.status_code}
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("FHIR transaction attempt failed host=%s attempt=%d error_type=%s", safe_host, attempt, type(exc).__name__)
                if attempt == self.max_attempts:
                    raise RuntimeError("FHIR test server transaction failed") from None
                await asyncio.sleep(self.backoff_seconds * (2 ** (attempt - 1)))
        raise RuntimeError("FHIR test server transaction failed")


def get_fhir_server_provider() -> ConfiguredFHIRServerProvider:
    if not settings.fhir_test_server_url.strip():
        raise ValueError("FHIR test server URL is not configured")
    return ConfiguredFHIRServerProvider(
        settings.fhir_test_server_url,
        max_attempts=settings.fhir_push_max_attempts,
        backoff_seconds=settings.fhir_push_backoff_seconds,
    )
