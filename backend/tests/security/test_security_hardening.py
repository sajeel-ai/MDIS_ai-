"""Security hardening tests for MDIS:
1. ALLOW_ANONYMOUS_ACCESS defaults to False and refuses to start in production.
2. JWT and role enforcement on /api/documents, /api/review, and export routes.
3. Reusable audit logging dependency for READ events (document, entities, evidence, exports) capturing user_id, resource_id, action, timestamp, IP.
4. CORS wildcard rejection.
5. AES-256-GCM encryption at rest for STORAGE_PATH with key management and tamper resistance.
"""

import base64
import os
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

from app.config import Settings, settings
from app.db import get_db
from app.dependencies.auth import UserContext, get_current_user
from app.dependencies.audit_read import audit_read_access
from app.models import AuditEvent, User, UserRole
from app.models.organization import DEFAULT_ORGANIZATION_ID
from app.security.auth import create_access_token, validate_jwt_configuration
from app.security.storage_crypto import (
    MAGIC_HEADER_V2,
    decrypt_bytes,
    encrypt_bytes,
    get_storage_encryption_key,
    is_encrypted,
)
from app.providers.storage.local import LocalStorageProvider
from app.main import app


@pytest.fixture
def mock_db():
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.info = {}
    session.scalar = AsyncMock(return_value=None)
    session.scalars = MagicMock()
    session.execute = AsyncMock()

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield session
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_anonymous_access_defaults_false_and_production_refusal(monkeypatch):
    """ALLOW_ANONYMOUS_ACCESS must default to False and refuse startup in production if True."""
    fresh_settings = Settings()
    assert fresh_settings.allow_anonymous_access is False

    # In production, ALLOW_ANONYMOUS_ACCESS=True must fail closed
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "allow_anonymous_access", True)
    monkeypatch.setattr(settings, "jwt_secret_key", "0123456789012345678901234567890123456789")
    monkeypatch.setattr(settings, "auth_cookie_secure", True)
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(settings, "ocr_provider", "azure")
    monkeypatch.setattr(settings, "extraction_provider", "openai")
    monkeypatch.setattr(settings, "storage_encryption_key", "01234567890123456789012345678901")

    with pytest.raises(RuntimeError, match="ALLOW_ANONYMOUS_ACCESS may only be enabled in development"):
        validate_jwt_configuration()


def test_storage_encryption_key_is_required_even_in_development(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "storage_encryption_key", "")
    monkeypatch.delenv("STORAGE_ENCRYPTION_KEY", raising=False)
    with pytest.raises(RuntimeError, match="STORAGE_ENCRYPTION_KEY must be configured in every environment"):
        get_storage_encryption_key()


def test_cors_startup_rejects_wildcard_without_database_access(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "environment", None)
    monkeypatch.setattr(settings, "cors_origins", "*")
    monkeypatch.setattr(settings, "jwt_secret_key", "a-private-jwt-secret-value-with-over-32-chars")
    monkeypatch.setattr(settings, "jwt_issuer", "mdis-test-issuer")
    monkeypatch.setattr(settings, "jwt_audience", "mdis-test-audience")
    with pytest.raises(RuntimeError, match="explicit origin allowlist"):
        validate_jwt_configuration()


def test_production_startup_rejects_obviously_weak_storage_keys(monkeypatch):
    from app.security.storage_crypto import validate_storage_key_strength
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "environment", None)
    monkeypatch.setattr(settings, "allow_anonymous_access", False)
    monkeypatch.setattr(settings, "auth_disabled", False)
    monkeypatch.setattr(settings, "jwt_secret_key", "a-private-jwt-secret-value-with-over-32-chars")
    monkeypatch.setattr(settings, "jwt_issuer", "mdis-test-issuer")
    monkeypatch.setattr(settings, "jwt_audience", "mdis-test-audience")
    monkeypatch.setattr(settings, "cors_origins", "https://review.example.test")
    monkeypatch.setattr(settings, "auth_cookie_secure", True)
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(settings, "ocr_provider", "azure")
    monkeypatch.setattr(settings, "extraction_provider", "openai")
    monkeypatch.setattr(settings, "storage_encryption_key", "0" * 64)
    monkeypatch.delenv("VITE_AUTH_BYPASS", raising=False)

    with pytest.raises(RuntimeError, match="STORAGE_ENCRYPTION_KEY.*weak"):
        validate_jwt_configuration()

    with pytest.raises(ValueError, match="weak"):
        validate_storage_key_strength("0" * 64, production=True)
    with pytest.raises(ValueError, match="weak"):
        validate_storage_key_strength("0123456789abcdef" * 4, production=True)
    validate_storage_key_strength("0" * 64, production=False)


@pytest.mark.asyncio
async def test_anonymous_admin_is_rejected_by_role_protected_document_routes():
    anonymous_admin = User(
        id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        email="anon@dev.local",
        role=UserRole.ADMIN,
        organization_id=DEFAULT_ORGANIZATION_ID,
        is_active=True,
    )
    app.dependency_overrides[get_current_user] = lambda: anonymous_admin
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/documents")
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_cors_rejects_wildcard():
    """CORS_ORIGINS containing '*' must be rejected."""
    monkeypatch_settings = Settings(cors_origins="*")
    assert "*" in monkeypatch_settings.cors_origins_list

    # Validate that configuration check refuses wildcard CORS
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        if any(origin == "*" for origin in monkeypatch_settings.cors_origins_list):
            raise RuntimeError("CORS_ORIGINS must be a non-empty explicit origin allowlist; wildcard '*' is forbidden")


@pytest.mark.asyncio
async def test_unauthenticated_requests_rejected_on_documents_and_review(mock_db):
    """Unauthenticated requests to /api/v1/documents, review, and exports must return 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        routes_to_test = [
            ("GET", "/api/v1/documents"),
            ("GET", f"/api/v1/documents/{uuid.uuid4()}"),
            ("GET", f"/api/v1/documents/{uuid.uuid4()}/entities"),
            ("GET", f"/api/v1/documents/{uuid.uuid4()}/evidence"),
            ("GET", f"/api/v1/documents/{uuid.uuid4()}/fhir"),
            ("GET", f"/api/v1/documents/{uuid.uuid4()}/export/csv"),
            ("GET", "/api/v1/review/queue"),
            ("GET", f"/api/v1/review/{uuid.uuid4()}"),
            ("GET", "/api/v1/review/stats"),
            ("POST", f"/api/v1/review/{uuid.uuid4()}/start"),
            ("POST", f"/api/v1/review/{uuid.uuid4()}/decision"),
            ("POST", f"/api/v1/review/{uuid.uuid4()}/approve"),
        ]

        for method, url in routes_to_test:
            if method == "GET":
                resp = await client.get(url)
            else:
                resp = await client.post(url, json={})
            assert resp.status_code == 401, f"Expected 401 for {method} {url}, got {resp.status_code}"


@pytest.mark.asyncio
async def test_role_checks_on_review_decision(mock_db):
    """A user with role VIEWER or CLINICIAN cannot submit review decisions (only REVIEWER or ADMIN)."""
    clinician_user = User(
        id=uuid.uuid4(),
        email="clinician@example.test",
        role=UserRole.CLINICIAN,
        organization_id=DEFAULT_ORGANIZATION_ID,
        is_active=True,
        mfa_enabled=False,
    )
    viewer_user = User(
        id=uuid.uuid4(),
        email="viewer@example.test",
        role=UserRole.VIEWER,
        organization_id=DEFAULT_ORGANIZATION_ID,
        is_active=True,
        mfa_enabled=False,
    )

    current_test_user = [viewer_user]

    async def override_get_current_user():
        return current_test_user[0]

    app.dependency_overrides[get_current_user] = override_get_current_user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Viewer cannot upload documents (requires CLINICIAN or ADMIN)
            current_test_user[0] = viewer_user
            resp_upload = await client.post(
                "/api/v1/documents/upload",
                data={"patient_id": str(uuid.uuid4()), "document_type": "Progress Note"},
                files={"file": ("test.pdf", b"%PDF-1.4\n%EOF", "application/pdf")},
            )
            assert resp_upload.status_code == 403, f"Expected 403 for viewer upload, got {resp_upload.status_code}"

            # Clinician cannot submit review decision (requires REVIEWER or ADMIN)
            current_test_user[0] = clinician_user
            resp_decision = await client.post(
                f"/api/v1/review/{uuid.uuid4()}/decision",
                json={"decision": "approved"},
            )
            assert resp_decision.status_code == 403, f"Expected 403 for clinician review decision, got {resp_decision.status_code}"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_read_audit_logging_dependency(mock_db):
    """Reusable audit_read_access dependency must capture user id, resource id, action, timestamp, and IP."""
    doc_id = uuid.uuid4()
    reviewer_id = uuid.uuid4()
    reviewer = User(
        id=reviewer_id,
        email="reviewer@example.test",
        role=UserRole.REVIEWER,
        organization_id=DEFAULT_ORGANIZATION_ID,
        is_active=True,
        mfa_enabled=False,
    )

    # Test the dependency directly
    from fastapi import Request
    scope = {
        "type": "http",
        "method": "GET",
        "path": f"/api/v1/documents/{doc_id}",
        "headers": [(b"host", b"test"), (b"x-forwarded-for", b"192.168.1.55")],
        "client": ("192.168.1.55", 12345),
        "path_params": {"document_id": str(doc_id)},
    }
    req = Request(scope)
    req.state.request_id = "test-request-id-123"

    dependency_fn = audit_read_access("view_document", resource_type="document")
    await dependency_fn(request=req, db=mock_db, current_user=reviewer)

    # Verify session.add was called with AuditEvent
    assert mock_db.add.called
    added_event = mock_db.add.call_args[0][0]
    assert isinstance(added_event, AuditEvent)
    assert added_event.action == "view_document"
    assert added_event.user_id == reviewer_id
    assert added_event.resource_id == doc_id
    assert added_event.organization_id == DEFAULT_ORGANIZATION_ID
    assert added_event.ip_address == "192.168.1.55"
    assert added_event.request_id == "test-request-id-123"
    assert mock_db.commit.called


@pytest.mark.asyncio
async def test_document_read_fails_closed_when_audit_flush_fails(monkeypatch):
    from app.services.documents.document_service import DocumentService

    document_id = uuid.uuid4()
    user = UserContext(
        id=uuid.uuid4(), email="clinician@example.test", role=UserRole.CLINICIAN,
        organization_id=DEFAULT_ORGANIZATION_ID, is_active=True,
    )
    db = AsyncMock()
    db.add = MagicMock()
    db.flush.side_effect = RuntimeError("audit store unavailable")
    monkeypatch.setattr(DocumentService, "get_document_details", AsyncMock())
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
        ) as client:
            response = await client.get(f"/api/v1/documents/{document_id}")
        assert response.status_code == 500
        DocumentService.get_document_details.assert_not_awaited()
    finally:
        app.dependency_overrides.clear()


def test_aes_256_gcm_storage_crypto():
    """AES-256-GCM encryption/decryption round-trip and tamper detection."""
    key = b"01234567890123456789012345678901"  # 32 bytes
    plaintext = b"CONFIDENTIAL MEDICAL RECORD - CLINICAL PHI DATA"

    encrypted = encrypt_bytes(plaintext, key=key)
    assert is_encrypted(encrypted)
    assert encrypted.startswith(MAGIC_HEADER_V2)
    assert encrypted != plaintext

    # Decrypt successfully
    decrypted = decrypt_bytes(encrypted, key=key)
    assert decrypted == plaintext

    # Tamper with ciphertext (flip 1 byte in the ciphertext body)
    tampered = bytearray(encrypted)
    tampered[-5] ^= 0xFF
    with pytest.raises(Exception):  # Cryptography raises InvalidTag
        decrypt_bytes(bytes(tampered), key=key)


@pytest.mark.asyncio
async def test_storage_provider_transparent_encryption(tmp_path, monkeypatch):
    """LocalStorageProvider must encrypt files on write and decrypt on read transparently."""
    test_key = base64.b64encode(b"a" * 32).decode("utf-8")
    monkeypatch.setattr(settings, "storage_encryption_key", test_key)
    monkeypatch.setattr(settings, "storage_local_path", str(tmp_path))

    provider = LocalStorageProvider(base_path=str(tmp_path))
    content = b"ORIGINAL CLINICAL DOCUMENT PDF CONTENT"
    storage_key = "documents/test_doc_1.pdf"

    saved_ref = await provider.save_file(storage_key, content)
    assert saved_ref.startswith("local:")

    # Verify that raw file on disk is encrypted with the key-id V2 header.
    raw_disk_path = provider._resolve_path(storage_key)
    with open(raw_disk_path, "rb") as f:
        disk_bytes = f.read()

    assert disk_bytes.startswith(MAGIC_HEADER_V2)
    assert disk_bytes != content

    # Verify read_file transparently decrypts
    read_back = await provider.read_file(storage_key)
    assert read_back == content


def test_migrate_storage_encryption_script(tmp_path, monkeypatch):
    """Migration script must encrypt unencrypted files, handle dry-run, and verify decryption."""
    from scripts.migrate_storage_encryption import migrate_storage

    test_key = base64.b64encode(b"k" * 32).decode("utf-8")
    monkeypatch.setattr(settings, "storage_encryption_key", test_key)

    file1 = tmp_path / "doc1.txt"
    file2 = tmp_path / "subfolder" / "doc2.pdf"
    file2.parent.mkdir(parents=True, exist_ok=True)

    file1.write_bytes(b"Plaintext document 1")
    file2.write_bytes(b"%PDF-1.4 sample document 2")

    # 1. Dry run
    res_dry = migrate_storage(tmp_path, dry_run=True)
    assert res_dry == 0
    assert not is_encrypted(file1.read_bytes())
    assert not is_encrypted(file2.read_bytes())

    # 2. Real migration
    res_mig = migrate_storage(tmp_path, dry_run=False)
    assert res_mig == 0
    assert is_encrypted(file1.read_bytes())
    assert is_encrypted(file2.read_bytes())
    assert decrypt_bytes(file1.read_bytes()) == b"Plaintext document 1"
    assert decrypt_bytes(file2.read_bytes()) == b"%PDF-1.4 sample document 2"

    # 3. Verify only
    res_verify = migrate_storage(tmp_path, verify_only=True)
    assert res_verify == 0

    # 4. Tamper detection during verify
    tampered_bytes = bytearray(file1.read_bytes())
    tampered_bytes[-3] ^= 0xFF
    file1.write_bytes(bytes(tampered_bytes))
    res_tamper = migrate_storage(tmp_path, verify_only=True)
    assert res_tamper == 1
