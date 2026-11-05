"""Secret resolution with environment, *_FILE, and future manager support."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol, runtime_checkable
from urllib.parse import urlparse


@runtime_checkable
class SecretManager(Protocol):
    def get(self, name: str) -> str | None:
        """Return a secret value, or None when it is not configured."""


class SecretManagerAdapter(SecretManager, Protocol):
    """Adapter contract for a named cloud secret manager."""


class EnvironmentSecretProvider:
    def __init__(
        self,
        values: Mapping[str, str] | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self._values = dict(values or {})
        self._environ = environ if environ is not None else os.environ

    def get(self, name: str) -> str | None:
        direct = self._values.get(name, self._environ.get(name))
        if direct is not None and direct.strip():
            return direct.strip()
        file_name = f"{name}_FILE"
        file_path = self._values.get(file_name, self._environ.get(file_name))
        if file_path and file_path.strip():
            try:
                value = Path(file_path).read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise RuntimeError(f"{file_name} points to an unreadable secret file") from exc
            if value:
                return value
        return None

    def require(self, name: str) -> str:
        value = self.get(name)
        if not value:
            raise RuntimeError(f"{name} must be configured")
        return value


@dataclass(frozen=True)
class MissingSecret:
    name: str
    reason: str


_PLACEHOLDER_MARKERS = ("changeme", "change-this", "replace", "example", "password", "secret")


def configured_secret(
    name: str,
    configured_value: str = "",
    provider: SecretManager | None = None,
) -> str:
    if configured_value.strip():
        return configured_value.strip()
    return (provider or EnvironmentSecretProvider()).get(name) or ""


def validate_required_secrets(
    config,
    provider: SecretManager | None = None,
) -> list[MissingSecret]:
    if not (
        config.app_env.strip().lower() in {"production", "prod"}
        or (config.environment or "").strip().lower() in {"production", "prod"}
    ):
        return []

    source = provider or EnvironmentSecretProvider()
    required = {
        "JWT_SECRET_KEY": configured_secret("JWT_SECRET_KEY", config.jwt_secret_key, source),
        "STORAGE_ENCRYPTION_KEY": configured_secret(
            "STORAGE_ENCRYPTION_KEY", config.storage_encryption_key, source
        ),
        "AUTH_ENCRYPTION_KEY": configured_secret(
            "AUTH_ENCRYPTION_KEY", config.auth_encryption_key, source
        ),
    }
    parsed = urlparse(config.database_url)
    if not parsed.password:
        required["DATABASE_PASSWORD"] = source.get("DATABASE_PASSWORD") or ""
    if config.email_provider.strip().lower() == "smtp":
        required["SMTP_PASSWORD"] = configured_secret("SMTP_PASSWORD", config.smtp_password, source)
    if config.extraction_provider.strip().lower() in {"openai", "hybrid"}:
        required["OPENAI_API_KEY"] = configured_secret("OPENAI_API_KEY", config.openai_api_key, source)

    failures: list[MissingSecret] = []
    for name, value in required.items():
        normalized = value.strip().casefold()
        if not normalized:
            failures.append(MissingSecret(name, "missing"))
        elif (
            name in {"JWT_SECRET_KEY", "STORAGE_ENCRYPTION_KEY", "AUTH_ENCRYPTION_KEY"}
            and len(value.strip()) < 32
        ) or any(marker in normalized for marker in _PLACEHOLDER_MARKERS):
            failures.append(MissingSecret(name, "weak or placeholder"))
    return failures
