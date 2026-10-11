"""Tests for the user-facing document lifecycle projection and list filters."""

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.documents.document_service import DocumentService
from app.workflows.states import derive_lifecycle_status


@pytest.fixture
def tmp_path():
    """Use a workspace-local directory when the managed temp root is ACL-locked."""
    path = Path.cwd() / ".document-lifecycle-test-tmp"
    path.mkdir(exist_ok=True)
    return path


def test_lifecycle_status_precedence_covers_every_processing_review_combination():
    expected = {
        "failed": "failed",
        "processing": "processing",
        "uploaded": "uploaded",
        "queued": "uploaded",
    }
    for processing, lifecycle in expected.items():
        for review in ("not_required", "pending", "in_review", "approved", "rejected"):
            assert derive_lifecycle_status(processing, review) == lifecycle

    for review, lifecycle in (
        ("rejected", "rejected"),
        ("approved", "approved"),
        ("in_review", "in_review"),
        ("pending", "in_review"),
        ("not_required", "extracted"),
    ):
        assert derive_lifecycle_status("completed", review) == lifecycle


def test_reextract_state_is_not_reported_as_approved_while_queued():
    assert derive_lifecycle_status("queued", "approved") == "uploaded"


@pytest.mark.asyncio
async def test_document_list_applies_org_status_unlinked_search_and_pagination_filters():
    session = MagicMock()
    count_result = MagicMock()
    count_result.scalar.return_value = 0
    rows_result = MagicMock()
    rows_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(side_effect=[count_result, rows_result])

    organization_id = uuid.uuid4()
    await DocumentService(session).list_documents(
        page=3,
        page_size=10,
        status="approved",
        search="MRN-42",
        unlinked_patient=True,
        sort="name_asc",
        organization_id=organization_id,
    )

    assert session.execute.await_count == 2
    count_sql = str(session.execute.await_args_list[0].args[0])
    page_sql = str(session.execute.await_args_list[1].args[0])
    for fragment in ("documents.organization_id", "documents.review_status", "documents.patient_id", "patients.mrn"):
        assert fragment in count_sql
    assert "LIMIT :param_1" in page_sql
    assert "OFFSET :param_2" in page_sql


@pytest.mark.asyncio
async def test_document_list_keeps_organization_predicate_when_no_optional_filters():
    session = MagicMock()
    count_result = MagicMock()
    count_result.scalar.return_value = 0
    rows_result = MagicMock()
    rows_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(side_effect=[count_result, rows_result])

    await DocumentService(session).list_documents(organization_id=uuid.uuid4())

    assert "documents.organization_id" in str(session.execute.await_args_list[0].args[0])
