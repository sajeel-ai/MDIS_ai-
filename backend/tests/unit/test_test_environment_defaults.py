"""Test-only defaults must be limited to disposable test databases."""

import os

import conftest


def test_test_database_gets_synthetic_storage_key_only_when_missing(monkeypatch):
    monkeypatch.delenv("STORAGE_ENCRYPTION_KEY", raising=False)

    assert conftest.set_test_storage_key_for_database(
        "postgresql+asyncpg://test:test@localhost:5433/mdis_test"
    ) is True
    assert os.environ["STORAGE_ENCRYPTION_KEY"] == conftest.TEST_STORAGE_ENCRYPTION_KEY


def test_test_database_does_not_override_explicit_storage_key(monkeypatch):
    monkeypatch.setenv("STORAGE_ENCRYPTION_KEY", "explicit-test-key")

    assert conftest.set_test_storage_key_for_database(
        "postgresql+asyncpg://test:test@localhost:5433/mdis_test"
    ) is True
    assert os.environ["STORAGE_ENCRYPTION_KEY"] == "explicit-test-key"


def test_non_test_database_does_not_get_test_storage_key(monkeypatch):
    monkeypatch.delenv("STORAGE_ENCRYPTION_KEY", raising=False)

    assert conftest.set_test_storage_key_for_database(
        "postgresql+asyncpg://test:test@localhost:5433/cognate_ai"
    ) is False
    assert "STORAGE_ENCRYPTION_KEY" not in os.environ
