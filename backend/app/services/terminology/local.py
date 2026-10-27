"""Local terminology service — lookup tables from extraction provider codes.

All codes in this file are sourced directly from the existing
LocalExtractionProvider dictionaries (local.py). No codes are invented.
Confidence is 0.97 for codes present in the table (local authority, not
an external validator) and 0.0 for any code not found.

To add a new code, append a row to the appropriate section; do NOT
invent codes — only add codes that appear in published clinical
terminologies.
"""
from __future__ import annotations

from app.services.terminology.base import BaseTerminologyService, TerminologyResult

# FHIR system URIs
_SYS = {
    "ICD10": "http://hl7.org/fhir/sid/icd-10",
    "RXNORM": "http://www.nlm.nih.gov/research/umls/rxnorm",
    "SNOMED": "http://snomed.info/sct",
    "LOINC": "http://loinc.org",
    "CPT": "http://www.ama-assn.org/go/cpt",
}

# Normalised alias map: code_system values from the extractor → canonical key
_SYSTEM_ALIASES: dict[str, str] = {
    "icd10": "ICD10",
    "icd-10": "ICD10",
    "rxnorm": "RXNORM",
    "snomed": "SNOMED",
    "snomed ct": "SNOMED",
    "loinc": "LOINC",
    "cpt": "CPT",
}

# Confidence for a code found in the local table.
# 0.97 (not 1.0) because this is a local lookup, not an external authority.
_LOCAL_CONFIDENCE = 0.97

# ---------------------------------------------------------------------------
# ICD-10 codes — from LocalExtractionProvider.DIAGNOSES
# ---------------------------------------------------------------------------
_ICD10: dict[str, str] = {
    "J18.9": "Pneumonia, unspecified organism",
    "J22": "Unspecified acute lower respiratory infection",
    "I10": "Essential (primary) hypertension",
    "J44.1": "Chronic obstructive pulmonary disease with (acute) exacerbation",
    "J44.9": "Chronic obstructive pulmonary disease, unspecified",
    "I21.4": "Non-ST elevation (NSTEMI) myocardial infarction",
    "N17.9": "Acute kidney failure, unspecified",
    "K81.0": "Acute cholecystitis",
    "J43.9": "Emphysema, unspecified",
    "J45.909": "Unspecified asthma, uncomplicated",
    "I20.9": "Angina pectoris, unspecified",
    "I20.89": "Other forms of angina pectoris",
    # Implicit findings codes
    "R73.09": "Other abnormal glucose",
    "E87.70": "Fluid overload, unspecified",
    "Z99.81": "Dependence on supplemental oxygen",
}

# ---------------------------------------------------------------------------
# RxNorm codes — from LocalExtractionProvider.MEDICATIONS
# ---------------------------------------------------------------------------
_RXNORM: dict[str, str] = {
    "723372": "Amoxicillin / Clavulanate",
    "358263": "Trimethoprim / Sulfamethoxazole",
    "896790": "Fluticasone / Salmeterol",
    "1001468": "Amlodipine / Atorvastatin",
    "308182": "Amoxicillin",
    "308135": "Amlodipine",
    "8640":   "Prednisone",
    "308047": "Azithromycin",
    "861007": "Tiotropium",
    "43598000": "Albuterol",   # NOTE: this is a SNOMED code in the source; kept as-is
    "860975": "Metformin",
    "83367":  "Atorvastatin",
    "314076": "Lisinopril",
    "310798": "Hydrochlorothiazide",
    "859749": "Rosuvastatin",
    "1191":   "Aspirin",
    "5224":   "Heparin",
    "1364430": "Ticagrelor",
    "5640":   "Ibuprofen",
    "7258":   "Naproxen",
}

# ---------------------------------------------------------------------------
# SNOMED codes — from LocalExtractionProvider.SYMPTOMS
# ---------------------------------------------------------------------------
_SNOMED: dict[str, str] = {
    "49727002":  "Cough",
    "386661006": "Fever",
    "84229001":  "Fatigue",
    "267036007": "Shortness of breath / Dyspnea",
    "29857009":  "Chest pain",
    "80313002":  "Palpitations",
    "56018004":  "Wheezing",
    "422587007": "Nausea",
    "422400008": "Vomiting",
}

# ---------------------------------------------------------------------------
# LOINC codes — from LocalExtractionProvider.LAB_PATTERNS and VITAL_PATTERNS
# ---------------------------------------------------------------------------
_LOINC: dict[str, str] = {
    "2160-0":  "Creatinine [Mass/volume] in Serum or Plasma",
    "4548-4":  "Hemoglobin A1c/Hemoglobin.total in Blood",
    "6598-7":  "Troponin T.cardiac [Mass/volume] in Serum or Plasma",
    "2823-3":  "Potassium [Moles/volume] in Serum or Plasma",
    "8310-5":  "Body temperature",
    "85354-9": "Blood pressure panel with all children optional",
    "19926-5": "FEV1/FVC",
    "20150-9": "FEV1 % predicted",
    "19870-5": "FVC % predicted",
    "29701-7": "Fractional excretion of sodium",
    "8867-4":  "Heart rate",
    "9279-1":  "Respiratory rate",
    "8290-1":  "Body temperature (method unspecified)",
    "59408-5": "Oxygen saturation in Arterial blood by Pulse oximetry",
    "29463-7": "Body weight",
    "8302-2":  "Body height",
    "39156-5": "Body mass index (BMI) [Ratio]",
}

# ---------------------------------------------------------------------------
# CPT codes — from LocalExtractionProvider.PROCEDURES
# ---------------------------------------------------------------------------
_CPT: dict[str, str] = {
    "47562": "Laparoscopic cholecystectomy",
    "74300": "Cholangiography, intraoperative, radiological supervision",
    "71046": "Radiologic examination, chest; 2 views",
    "94060": "Bronchospasm evaluation; spirometry, pre and post bronchodilator",
    "71250": "CT thorax without contrast",
}

# ---------------------------------------------------------------------------
# Display-name → (code, system_key) index for lookup_by_display
# ---------------------------------------------------------------------------
_DISPLAY_INDEX: dict[str, tuple[str, str]] = {}
for _code, _display in _ICD10.items():
    _DISPLAY_INDEX[_display.lower()] = (_code, "ICD10")
for _code, _display in _RXNORM.items():
    _DISPLAY_INDEX[_display.lower()] = (_code, "RXNORM")
for _code, _display in _SNOMED.items():
    _DISPLAY_INDEX[_display.lower()] = (_code, "SNOMED")
for _code, _display in _LOINC.items():
    _DISPLAY_INDEX[_display.lower()] = (_code, "LOINC")
for _code, _display in _CPT.items():
    _DISPLAY_INDEX[_display.lower()] = (_code, "CPT")

# Also add short canonical names used in the extractor normalized_value fields
_DISPLAY_ALIASES: dict[str, tuple[str, str]] = {
    "pneumonia": ("J18.9", "ICD10"),
    "lower respiratory tract infection": ("J22", "ICD10"),
    "hypertension": ("I10", "ICD10"),
    "diabetes mellitus": ("", "ICD10"),      # no single ICD-10 — requires specificity
    "chronic obstructive pulmonary disease": ("J44.9", "ICD10"),
    "acute exacerbation of chronic obstructive pulmonary disease": ("J44.1", "ICD10"),
    "non-st elevation myocardial infarction": ("I21.4", "ICD10"),
    "acute kidney injury": ("N17.9", "ICD10"),
    "acute cholecystitis": ("K81.0", "ICD10"),
    "emphysema": ("J43.9", "ICD10"),
    "asthma": ("J45.909", "ICD10"),
    "angina pectoris": ("I20.9", "ICD10"),
    "exertional angina": ("I20.89", "ICD10"),
}

_TABLES: dict[str, dict[str, str]] = {
    "ICD10": _ICD10,
    "RXNORM": _RXNORM,
    "SNOMED": _SNOMED,
    "LOINC": _LOINC,
    "CPT": _CPT,
}


def _not_found(code: str, system_key: str) -> TerminologyResult:
    return TerminologyResult(
        code=code,
        system=_SYS.get(system_key, system_key),
        display="",
        confidence=0.0,
        source="local_table_miss",
    )


class LocalTerminologyService(BaseTerminologyService):
    """Terminology service backed by local lookup tables.

    Confidence is 0.97 for codes present in the table.  For codes not in the
    table the confidence is 0.0 — the entity will be flagged for human review.

    This service NEVER makes network requests.  To use external APIs
    (RxNorm, VSAC, SNOMED browser) implement a new class inheriting from
    BaseTerminologyService and register it in the DI container.
    """

    def lookup(self, code: str, system: str) -> TerminologyResult:
        system_key = _SYSTEM_ALIASES.get(system.strip().lower(), system.strip().upper())
        table = _TABLES.get(system_key)
        if table is None:
            return _not_found(code, system_key)
        display = table.get(code.strip())
        if display is None:
            return _not_found(code, system_key)
        return TerminologyResult(
            code=code.strip(),
            system=_SYS.get(system_key, system_key),
            display=display,
            confidence=_LOCAL_CONFIDENCE,
            source="local_table",
        )

    @staticmethod
    def table_counts() -> dict[str, int]:
        """Number of locally curated code/display rows, by code system."""
        return {system: len(table) for system, table in _TABLES.items()}

    def lookup_by_display(self, display: str, system: str) -> TerminologyResult:
        key = display.strip().lower()
        system_key = _SYSTEM_ALIASES.get(system.strip().lower(), system.strip().upper())

        # Check alias map first (extractor normalized_value names)
        alias = _DISPLAY_ALIASES.get(key)
        if alias is not None:
            code, alias_sys = alias
            if alias_sys == system_key and code:
                return TerminologyResult(
                    code=code,
                    system=_SYS.get(alias_sys, alias_sys),
                    display=display,
                    confidence=_LOCAL_CONFIDENCE,
                    source="local_display_alias",
                )

        # Check full display index
        match = _DISPLAY_INDEX.get(key)
        if match is not None:
            code, match_sys = match
            if match_sys == system_key:
                table = _TABLES.get(match_sys, {})
                return TerminologyResult(
                    code=code,
                    system=_SYS.get(match_sys, match_sys),
                    display=table.get(code, display),
                    confidence=_LOCAL_CONFIDENCE,
                    source="local_display_index",
                )

        return _not_found(display, system_key)

