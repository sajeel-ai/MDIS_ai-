"""Unsupported clinical upload extensions fail with an explicit 415 response."""
import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import get_db
from app.dependencies.auth import UserContext, UserRole, get_current_user
from app.main import app


@pytest.mark.asyncio
@pytest.mark.parametrize("filename", ["record.docx", "record.rtf", "record.html", "record.dcm"])
async def test_unsupported_clinical_file_formats_return_415(filename: str):
    user = UserContext(
        id=uuid.uuid4(), email="clinician@example.test", role=UserRole.CLINICIAN,
        organization_id=uuid.uuid4(), is_active=True,
    )
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/documents/upload",
                data={"patient_id": str(uuid.uuid4()), "document_type": "progress_note"},
                files={"file": (filename, b"fixture", "application/octet-stream")},
            )
        assert response.status_code == 415
        assert "Unsupported file type" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()
