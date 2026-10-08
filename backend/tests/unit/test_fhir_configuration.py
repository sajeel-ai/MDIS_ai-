"""Fail-closed FHIR target validation and CapabilityStatement checks."""

import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.mark.parametrize("url", ["ftp://localhost:8080/fhir", "localhost:8080/fhir", "http://user:pass@fhir.test/fhir"])
def test_fhir_url_rejects_unsafe_shape(url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, fhir_test_server_url=url)


@pytest.mark.parametrize("url", ["http://localhost:8080/fhir", "https://hapi.fhir.org/fhir"])
def test_production_rejects_localhost_and_public_hapi(url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", environment="production", fhir_test_server_url=url)


def test_development_accepts_local_hapi_target():
    settings = Settings(_env_file=None, fhir_test_server_url="http://localhost:8080/fhir")
    assert settings.fhir_test_server_url == "http://localhost:8080/fhir"
