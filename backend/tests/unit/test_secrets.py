import pytest

from app.config import Settings
from app.security.secrets import (
    EnvironmentSecretProvider,
    SecretManager,
    SecretManagerAdapter,
    validate_required_secrets,
)


def test_file_secret_is_used_without_logging_value(tmp_path, monkeypatch):
    secret_file = tmp_path / "jwt"
    secret_file.write_text("file-secret-value\n", encoding="utf-8")
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.setenv("JWT_SECRET_KEY_FILE", str(secret_file))

    provider = EnvironmentSecretProvider()

    assert provider.get("JWT_SECRET_KEY") == "file-secret-value"


def test_environment_secret_wins_over_file(tmp_path, monkeypatch):
    secret_file = tmp_path / "jwt"
    secret_file.write_text("file-secret-value", encoding="utf-8")
    monkeypatch.setenv("JWT_SECRET_KEY", "environment-secret")
    monkeypatch.setenv("JWT_SECRET_KEY_FILE", str(secret_file))

    assert EnvironmentSecretProvider().get("JWT_SECRET_KEY") == "environment-secret"


def test_missing_secret_is_explicit(monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY_FILE", raising=False)

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        EnvironmentSecretProvider().require("JWT_SECRET_KEY")


def test_secret_values_are_not_written_to_logs(caplog, tmp_path):
    secret_file = tmp_path / "smtp"
    secret_file.write_text("synthetic-secret-value", encoding="utf-8")
    provider = EnvironmentSecretProvider(
        values={"SMTP_PASSWORD_FILE": str(secret_file)},
        environ={},
    )

    with caplog.at_level("INFO"):
        assert provider.get("SMTP_PASSWORD") == "synthetic-secret-value"

    assert "synthetic-secret-value" not in caplog.text


def test_cloud_adapter_is_interface_only():
    assert issubclass(SecretManagerAdapter, SecretManager)


def test_production_required_secrets_are_rejected_without_values():
    config = Settings(
        app_env="production",
        environment="production",
        database_url="postgresql+asyncpg://app:strong-db-password@postgres:5433/cognate_prod",
        jwt_secret_key="",
        storage_encryption_key="",
        auth_encryption_key="",
        extraction_provider="openai",
        email_provider="smtp",
    )

    failures = validate_required_secrets(
        config,
        EnvironmentSecretProvider(values={}, environ={}),
    )

    assert {"JWT_SECRET_KEY", "STORAGE_ENCRYPTION_KEY", "AUTH_ENCRYPTION_KEY"} <= {
        failure.name for failure in failures
    }
    assert any(failure.name == "SMTP_PASSWORD" for failure in failures)
    assert any(failure.name == "OPENAI_API_KEY" for failure in failures)
