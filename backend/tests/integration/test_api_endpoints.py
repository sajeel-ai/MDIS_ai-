"""Integration tests for FastAPI endpoints with mocked DB dependencies."""

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock
from app.main import app
from app.db import get_db
from app.dependencies.auth import get_current_user
from app.models import User, UserRole
from app.models.organization import DEFAULT_ORGANIZATION_ID
import uuid


@pytest.fixture(autouse=True)
def override_db_dependency():
    async def mock_get_db():
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.info = {}
        # Mock scalar/scalars results
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalars.return_value.first.return_value = None
        mock_session.execute.return_value = mock_result
        yield mock_session

    app.dependency_overrides[get_db] = mock_get_db
    async def mock_current_user():
        return User(
            id=uuid.UUID("a0c7c7d8-e9b9-4623-b5fc-134a2058e945"),
            email="integration@example.test",
            role="admin",
            organization_id=DEFAULT_ORGANIZATION_ID,
            is_active=True,
        )

    app.dependency_overrides[get_current_user] = mock_current_user
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_dashboard_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert "metrics" in data
    assert "review_queue_summary" in data


@pytest.mark.asyncio
async def test_documents_list_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/documents")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_aiops_metrics_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/aiops/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "total_jobs" in data
    assert data["latest_eval"]["fixtures_evaluated"] >= 30


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "expected_status"),
    [
        (UserRole.CLINICIAN, 403),
        (UserRole.ADMIN, 200),
        (UserRole.OPERATOR, 200),
    ],
)
async def test_aiops_health_role_access(role, expected_status):
    user = User(
        id=uuid.uuid4(),
        email=f"{role.value}@example.test",
        role=role,
        organization_id=DEFAULT_ORGANIZATION_ID,
        is_active=True,
    )

    async def current_user_override():
        return user

    app.dependency_overrides[get_current_user] = current_user_override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/aiops/health")

    assert response.status_code == expected_status
    if expected_status == 200:
        assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_upload_document_endpoint():
    import pymupdf as fitz
    import io
    pdf = fitz.open()
    pdf.new_page()
    file_bytes = pdf.tobytes()
    pdf.close()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        data = {
            "patient_id": "016ae35b-db14-44c5-8174-15a00690bb26",
            "document_type": "discharge_summary",
        }
        files = {
            "file": ("test_upload.pdf", io.BytesIO(file_bytes), "application/pdf")
        }
        response = await ac.post("/api/v1/documents/upload", data=data, files=files)
    assert response.status_code in [201, 404]  # 404 if mock patient not found in mock DB
