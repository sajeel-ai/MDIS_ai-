"""Terminology service package."""
from app.services.terminology.base import BaseTerminologyService, TerminologyResult
from app.services.terminology.local import LocalTerminologyService

__all__ = ["BaseTerminologyService", "TerminologyResult", "LocalTerminologyService"]

