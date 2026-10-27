"""Unit tests verifying EHR outbound push is clearly labeled as simulation."""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.db import get_db
from app.dependencies.auth import UserContext, UserRole, get_current_user
from app.models import Document


@pytest.mark.asyncio
async def test_ehr_push_endpoint_returns_simulation_label():
    user = UserContext(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        role=UserRole.ADMIN,
        email="admin@cognate.test",
    )
    mock_db = AsyncMock()

    doc_id = uuid.uuid4()
    mock_doc = MagicMock(spec=Document)
    mock_doc.id = doc_id
    mock_doc.source = "synthetic"
    mock_doc.organization_id = user.organization_id

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_db

    fake_bundle = {"resourceType": "Bundle", "type": "transaction", "entry": []}
    fake_push_result = {"status": "success", "responses": []}

    try:
        with patch("app.routers.integrations.authorize_document_access", new=AsyncMock(return_value=mock_doc)), \
             patch("app.routers.integrations.FHIRProjectionService") as MockFHIR, \
             patch("app.routers.integrations.get_fhir_server_provider") as MockProvider, \
             patch("app.routers.integrations.record_audit_event", new=AsyncMock()), \
             patch("app.routers.integrations.settings") as mock_settings:

            mock_settings.api_prefix = "/api/v1"
            mock_settings.fhir_push_enabled = True
            mock_settings.smart_on_fhir_configured = False

            MockFHIR.return_value.generate_document_fhir_bundle = AsyncMock(return_value=fake_bundle)
            mock_provider_inst = MagicMock()
            mock_provider_inst.push_transaction = AsyncMock(return_value=fake_push_result)
            MockProvider.return_value = mock_provider_inst

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.post(f"/api/v1/integrations/fhir/push/{doc_id}")
                assert res.status_code == 200
                data = res.json()
                assert data["simulation"] is True
                assert data["mode"] == "simulation"
                assert data["smart_on_fhir_configured"] is False
    finally:
        app.dependency_overrides.clear()

