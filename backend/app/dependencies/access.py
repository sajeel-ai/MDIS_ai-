"""Resource-level access control helpers."""

import uuid
from app.dependencies.auth import UserContext


def verify_patient_access(patient_id: uuid.UUID, user: UserContext) -> None:
    """Placeholder for patient-level access boundary check."""
    pass


def verify_document_access(document_id: uuid.UUID, user: UserContext) -> None:
    """Placeholder for document-level access boundary check."""
    pass
