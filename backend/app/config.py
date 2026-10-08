"""
Cognate AI — Application Configuration

Uses pydantic-settings to load from environment variables or .env file.
All configuration is centralized here — no os.getenv() calls scattered
throughout the codebase.
"""

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal
from urllib.parse import urlparse


def _validate_fhir_url(url: str, app_env: str, environment: str | None) -> str:
    value = url.strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("FHIR_TEST_SERVER_URL must be an http(s) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("FHIR_TEST_SERVER_URL must not contain credentials")
    production = app_env.strip().lower() == "production" or (environment or "").strip().lower() == "production"
    host = (parsed.hostname or "").lower().rstrip(".")
    if production and (host == "localhost" or host.endswith(".localhost") or host in {"127.0.0.1", "::1", "hapi.fhir.org"} or host.endswith(".hapi.fhir.org")):
        raise ValueError("FHIR_TEST_SERVER_URL cannot target localhost or a public HAPI test server in production")
    return value.rstrip("/")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "cognate-ai-api"
    app_env: str = "development"
    # Some deployments use ENVIRONMENT while older app settings use APP_ENV.
    # Keep both visible so a conflicting production marker fails closed.
    environment: str | None = None
    debug: bool = False
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    api_prefix: str = "/api/v1"

    # Database
    database_url: str = ""

    # Storage
    storage_backend: str = "local"
    storage_local_path: str = "../storage"
    max_upload_size_bytes: int = 25 * 1024 * 1024
    max_document_pages: int = 50
    review_policy: Literal["all", "threshold"] = "all"
    review_confidence_threshold: float = Field(default=0.85, ge=0, le=1)
    review_high_priority_threshold: float = Field(default=0.60, ge=0, le=1)

    # Outbound FHIR is opt-in and may only receive synthetic/test documents.
    fhir_outbound_enabled: bool = False
    fhir_push_enabled: bool = False
    fhir_test_server_url: str = ""
    fhir_push_max_attempts: int = Field(default=3, ge=1, le=8)
    fhir_push_backoff_seconds: float = Field(default=0.5, ge=0, le=30)

    # Providers
    ocr_provider: str = "local"  # mock | local | azure
    azure_doc_intel_endpoint: str = ""
    azure_doc_intel_key: str = ""

    extraction_provider: str = "openai"  # local | mock | openai
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # Security
    jwt_secret_key: str = ""
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_issuer: str = "cognate-ai"
    jwt_audience: str = "cognate-ai-client"
    jwt_access_token_expire_minutes: int = Field(default=15, ge=1, le=15)
    refresh_token_expire_days: int = Field(default=7, ge=1, le=7)
    auth_session_expire_hours: int = Field(default=12, ge=1, le=168)
    auth_cookie_secure: bool = False
    auth_disabled: bool = False
    auth_lockout_attempts: int = Field(default=5, ge=1, le=20)
    auth_lockout_minutes: int = Field(default=15, ge=1, le=1440)
    auth_lockout_max_minutes: int = Field(default=1440, ge=15, le=10080)
    auth_rate_limit_window_seconds: int = Field(default=900, ge=60, le=86400)
    auth_rate_limit_per_ip: int = Field(default=30, ge=1, le=10000)
    auth_rate_limit_per_account: int = Field(default=10, ge=1, le=1000)
    auth_enumeration_min_response_ms: int = Field(default=300, ge=0, le=5000)
    password_blocklist: str = "password,123456789012,1234567890123,qwerty123456,letmein123456"
    password_blocklist_file: str = ""
    auth_encryption_key: str = ""
    registration_mode: Literal["approval", "invite_only", "disabled"] = "approval"
    email_provider: Literal["", "smtp", "resend", "sendgrid"] = ""
    email_from: str = ""
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = Field(default="", validation_alias=AliasChoices("SMTP_USER", "SMTP_USERNAME"))
    smtp_password: str = ""
    smtp_starttls: bool = True
    email_send_timeout_seconds: float = Field(default=10, gt=0, le=60)
    email_retry_attempts: int = Field(default=3, ge=1, le=8)
    email_retry_backoff_seconds: float = Field(default=0.25, ge=0, le=30)
    email_code_cooldown_seconds: int = Field(default=60, ge=1, le=3600)
    email_code_daily_limit: int = Field(default=5, ge=1, le=100)
    email_code_max_attempts: int = Field(default=5, ge=1, le=20)
    resend_api_key: str = ""
    sendgrid_api_key: str = ""
    public_app_url: str = ""

    # CORS
    # Comma-separated string; parsed into a list by the property below.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8443,http://127.0.0.1:8443"

    @model_validator(mode="after")
    def validate_fhir_configuration(self):
        self.fhir_test_server_url = _validate_fhir_url(self.fhir_test_server_url, self.app_env, self.environment)
        return self

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()


def validate_fhir_configuration() -> None:
    settings.fhir_test_server_url = _validate_fhir_url(settings.fhir_test_server_url, settings.app_env, settings.environment)
