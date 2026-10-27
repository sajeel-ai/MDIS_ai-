"""Abstract base class for the MDIS terminology service.

A terminology service validates codes against standard vocabularies
(ICD-10, RxNorm, SNOMED CT, LOINC, CPT) and returns a confidence score.
Implementations:
  - LocalTerminologyService  — lookup tables seeded from the extraction provider
  - Future: RxNorm API, VSAC, SNOMED CT browser API
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class TerminologyResult:
    """Result of a single code or display-name lookup.

    Attributes:
        code:        The canonical code string (e.g. "J18.9").
        system:      The FHIR system URI (e.g. "http://hl7.org/fhir/sid/icd-10").
        display:     Human-readable display string.
        confidence:  Float in [0, 1].  0.0 → code not found / not verified.
                     1.0 → definitively verified from an authoritative source.
        source:      Which lookup source produced this result (for audit).
    """
    code: str
    system: str
    display: str
    confidence: float
    source: str = "unknown"


class BaseTerminologyService(ABC):
    """Interface that all terminology service implementations must satisfy."""

    @abstractmethod
    def lookup(self, code: str, system: str) -> TerminologyResult:
        """Return a TerminologyResult for the given code in the given coding system.

        If the code is not found, return a TerminologyResult with confidence=0.0.
        Never raise for a simple miss; only raise for configuration errors.
        """

    @abstractmethod
    def lookup_by_display(self, display: str, system: str) -> TerminologyResult:
        """Return a TerminologyResult for the best matching display name.

        Implementations should do case-insensitive matching.
        If no match is found, return a TerminologyResult with confidence=0.0.
        """

    def verify_entity_details(
        self,
        details: dict,
        confidence_threshold: float = 0.90,
    ) -> TerminologyResult | None:
        """Mutate *details* by adding ``code_verified`` (bool) and optionally
        ``terminology_confidence`` (float) and ``terminology_display`` (str).

        Returns the TerminologyResult used, or None if no code was present.
        """
        code = details.get("code")
        system = str(details.get("code_system") or "")

        if not code or not system:
            details["code_verified"] = False
            details["terminology_confidence"] = 0.0
            return None

        result = self.lookup(code=str(code), system=system)
        details["terminology_confidence"] = result.confidence
        details["code_verified"] = result.confidence >= confidence_threshold
        if result.display:
            details.setdefault("terminology_display", result.display)
        return result

