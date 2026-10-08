"""Deterministic local settings and isolated temp/storage paths for tests."""

import tempfile

import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def isolate_test_environment(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Do not inherit local .env auth/storage values or OS-global temp paths."""
    storage_path = tmp_path / "storage"
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(storage_path))
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "auth_disabled", False)
    monkeypatch.setattr(settings, "jwt_secret_key", "synthetic-test-jwt-secret-that-is-long-enough-123456")
    monkeypatch.setattr(settings, "auth_encryption_key", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
    monkeypatch.setattr(settings, "auth_rate_limit_per_ip", 10000)
    monkeypatch.setattr(settings, "auth_rate_limit_per_account", 10000)
    monkeypatch.setattr(settings, "storage_local_path", str(storage_path))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
