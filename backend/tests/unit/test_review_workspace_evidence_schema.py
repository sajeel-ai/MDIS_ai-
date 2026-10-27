from types import SimpleNamespace
import uuid

from app.schemas.extraction import EvidenceSpanResponse
from app.services.documents.document_service import _serialize_evidence_span


def test_evidence_response_preserves_page_number_for_multi_page_highlights():
    response = EvidenceSpanResponse.model_validate(
        {
            "id": "span-1",
            "entity_id": "entity-1",
            "start_offset": 0,
            "end_offset": 4,
            "exact_text": "Demo",
            "page_number": 2,
            "bbox": [0.1, 0.2, 0.4, 0.3],
        }
    )

    assert response.page_number == 2


def test_document_entity_serializer_returns_evidence_page_number():
    span = SimpleNamespace(
        id=uuid.uuid4(), entity_id=uuid.uuid4(), start_offset=0, end_offset=4,
        text="Demo", page_number=2, bbox=[0.1, 0.2, 0.4, 0.3],
    )
    response = _serialize_evidence_span(span)

    assert response["page_number"] == 2
