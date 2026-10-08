"""Cognate AI SQLAlchemy models — public API.

Imports all models so that alembic env.py can do:
    from app.models import Base
and see every table in Base.metadata.
"""

from app.db import Base  # noqa: F401 — re-exported

from app.models.user import RegistrationStatus, User  # noqa: F401
from app.models.refresh_token import RefreshToken  # noqa: F401
from app.models.auth_action_token import AuthActionToken, AuthRateLimitBucket, AuthVerificationCode  # noqa: F401
from app.models.roles import UserRole  # noqa: F401
from app.models.organization import Organization  # noqa: F401
from app.models.patient import Patient  # noqa: F401
from app.models.encounter import Encounter  # noqa: F401
from app.models.icd_code import IcdCode  # noqa: F401
from app.models.document import Document  # noqa: F401
from app.models.document_version import DocumentVersion  # noqa: F401
from app.models.processing import ProcessingJob, ProcessingStep  # noqa: F401
from app.models.extraction import Extraction  # noqa: F401
from app.models.clinical_entity import ClinicalEntity  # noqa: F401
from app.models.evidence import EvidenceSpan  # noqa: F401
from app.models.validation import ValidationResult  # noqa: F401
from app.models.review import ReviewTask  # noqa: F401
from app.models.audit import AuditEvent  # noqa: F401

__all__ = [
    "Base",
    "User",
    "RegistrationStatus",
    "RefreshToken",
    "AuthActionToken",
    "AuthRateLimitBucket",
    "AuthVerificationCode",
    "UserRole",
    "Organization",
    "Patient",
    "Encounter",
    "IcdCode",
    "Document",
    "DocumentVersion",
    "ProcessingJob",
    "ProcessingStep",
    "Extraction",
    "ClinicalEntity",
    "EvidenceSpan",
    "ValidationResult",
    "ReviewTask",
    "AuditEvent",
]
