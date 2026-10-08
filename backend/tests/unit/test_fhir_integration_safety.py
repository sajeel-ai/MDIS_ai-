"""Outbound FHIR remains disabled and rejects non-synthetic documents."""

import pytest
from fastapi import HTTPException
from app.config import Settings
from app.routers.integrations import ensure_synthetic_test_source


def test_outbound_fhir_defaults_to_disabled():
    assert Settings(_env_file=None).fhir_outbound_enabled is False
    assert Settings(_env_file=None).fhir_push_enabled is False


@pytest.mark.parametrize("source", ["synthetic", "test", "SYNTHETIC"])
def test_outbound_accepts_only_synthetic_test_sources(source):
    ensure_synthetic_test_source(source)


@pytest.mark.parametrize("source", ["upload", "mimic_demo", "mimic_note"])
def test_outbound_rejects_non_synthetic_sources(source):
    with pytest.raises(HTTPException) as error:
        ensure_synthetic_test_source(source)
    assert error.value.status_code == 422
