"""Local clinical information extraction provider.

Offline prototype provider.
Uses deterministic clinical terminology and regex patterns.
No external API or API key is required.
"""

import re

from app.providers.extraction.base import (
    BaseExtractionProvider,
    ExtractionResult,
    ExtractedEntityData,
)
from app.providers.extraction.context import detect_assertion, detect_section


class LocalExtractionProvider(BaseExtractionProvider):
    """Offline clinical entity extraction for prototype use."""

    # Diagnosis terminology commonly present in the prototype dataset.
    DIAGNOSES = {
        "pneumonia": ("Pneumonia", "J18.9", "ICD10"),
        "lower respiratory tract infection": (
            "Lower respiratory tract infection",
            "J22",
            "ICD10",
        ),
        "hypertension": ("Hypertension", "I10", "ICD10"),
        "diabetes mellitus": ("Diabetes mellitus", "", ""),
        "diabetes": ("Diabetes mellitus", "", ""),
        "acute copd exacerbation": (
            "Acute exacerbation of chronic obstructive pulmonary disease",
            "J44.1",
            "ICD10",
        ),
        "copd": ("Chronic obstructive pulmonary disease", "J44.9", "ICD10"),
        "nstemi": (
            "Non-ST elevation myocardial infarction",
            "I21.4",
            "ICD10",
        ),
        "acute kidney injury": (
            "Acute kidney injury",
            "N17.9",
            "ICD10",
        ),
        "acute cholecystitis": (
            "Acute cholecystitis",
            "K81.0",
            "ICD10",
        ),
        "emphysema": ("Emphysema", "J43.9", "ICD10"),
        "asthma": ("Asthma", "J45.909", "ICD10"),
        "angina": ("Angina pectoris", "I20.9", "ICD10"),
        "exertional angina": ("Exertional angina", "I20.89", "ICD10"),
    }

    SYMPTOMS = {
        "cough": ("Cough", "49727002", "SNOMED"),
        "fever": ("Fever", "386661006", "SNOMED"),
        "fatigue": ("Fatigue", "84229001", "SNOMED"),
        "shortness of breath": (
            "Shortness of breath",
            "267036007",
            "SNOMED",
        ),
        "dyspnea": ("Dyspnea", "267036007", "SNOMED"),
        "sob": ("Shortness of breath", "267036007", "SNOMED"),
        "chest pain": ("Chest pain", "29857009", "SNOMED"),
        "palpitations": ("Palpitations", "80313002", "SNOMED"),
        "wheezing": ("Wheezing", "56018004", "SNOMED"),
        "nausea": ("Nausea", "422587007", "SNOMED"),
        "vomiting": ("Vomiting", "422400008", "SNOMED"),
    }

    MEDICATIONS = {
        "amoxicillin": ("Amoxicillin", "308182", "RxNorm"),
        "amlodipine": ("Amlodipine", "308135", "RxNorm"),
        "prednisone": ("Prednisone", "8640", "RxNorm"),
        "azithromycin": ("Azithromycin", "308047", "RxNorm"),
        "tiotropium": ("Tiotropium", "861007", "RxNorm"),
        "albuterol": ("Albuterol", "43598000", "RxNorm"),
        "metformin": ("Metformin", "860975", "RxNorm"),
        "atorvastatin": ("Atorvastatin", "83367", "RxNorm"),
        "lisinopril": ("Lisinopril", "314076", "RxNorm"),
        "hydrochlorothiazide": (
            "Hydrochlorothiazide",
            "310798",
            "RxNorm",
        ),
        "rosuvastatin": ("Rosuvastatin", "859749", "RxNorm"),
        "aspirin": ("Aspirin", "1191", "RxNorm"),
        "heparin": ("Heparin", "5224", "RxNorm"),
        "ticagrelor": ("Ticagrelor", "1364430", "RxNorm"),
        "nsaid": ("Non-steroidal anti-inflammatory drug", "", "RxNorm"),
        "ibuprofen": ("Ibuprofen", "5640", "RxNorm"),
        "naproxen": ("Naproxen", "7258", "RxNorm"),
    }

    _DOSE_PATTERN = re.compile(
        r"\b(\d+(?:\.\d+)?)\s*(mg|mcg|µg|μg|ug|g|kg|ml|mL|l|meq|mmol|iu|units?|tablets?|capsules?)\b",
        re.IGNORECASE,
    )
    _FREQUENCY_PATTERN = re.compile(
        r"\b((?:once|twice|thrice|two|three|four)\s+(?:a|per)\s+day|"
        r"(?:\d+)\s+(?:a|per)\s+day|"
        r"(?:once|twice|three|four)\s+daily|"
        r"(?:\d+)\s+times?\s+(?:a|per)\s+day|"
        r"(?:every\s+\d+\s+(?:hours?|days?))|"
        r"(?:daily|q\.?\s*(?:d|day)|bid|tid|qid)\b)",
        re.IGNORECASE,
    )

    @classmethod
    def _medication_details(cls, text: str, start: int, end: int) -> dict[str, str]:
        """Capture dose and administration frequency near a medication mention."""
        # Prefer instructions after the medication name. This avoids assigning
        # the previous medication's dose when several medicines share a line.
        after_window = text[end:min(len(text), end + 100)]
        after_window = re.split(r"[\n;.]", after_window, maxsplit=1)[0]
        before_window = text[max(0, start - 45):start]
        details: dict[str, str] = {}
        dose = cls._DOSE_PATTERN.search(after_window) or cls._DOSE_PATTERN.search(before_window)
        if dose:
            details["dose"] = f"{dose.group(1)} {dose.group(2)}"
        frequency = cls._FREQUENCY_PATTERN.search(after_window) or cls._FREQUENCY_PATTERN.search(before_window)
        if frequency:
            details["frequency"] = " ".join(frequency.group(1).split())
        return details

    PROCEDURES = {
        "laparoscopic cholecystectomy": (
            "Laparoscopic cholecystectomy",
            "47562",
            "CPT",
        ),
        "intraoperative cholangiogram": (
            "Intraoperative cholangiogram",
            "74300",
            "CPT",
        ),
        "cholecystectomy": (
            "Cholecystectomy",
            "47562",
            "CPT",
        ),
        "chest x-ray": (
            "Chest X-ray",
            "71046",
            "CPT",
        ),
        "chest radiography": (
            "Chest radiography",
            "71046",
            "CPT",
        ),
        "ct thorax": (
            "CT thorax",
            "71250",
            "CPT",
        ),
        "spirometry": (
            "Spirometry",
            "94060",
            "CPT",
        ),
    }

    LAB_PATTERNS = [
        (
            r"\b(?:serum\s+)?creatinine\s*(?:was|of|=|:)?\s*(\d+(?:\.\d+)?)\s*mg/dL",
            "Creatinine",
            "LOINC",
            "2160-0",
        ),
        (
            r"\bhba1c\s*(?:was|of|=|:)?\s*(\d+(?:\.\d+)?)\s*%",
            "Hemoglobin A1c",
            "LOINC",
            "4548-4",
        ),
        (
            r"\btroponin\s+t\s*(?:was|of|=|:)?\s*(\d+(?:\.\d+)?)\s*ng/L",
            "Troponin T",
            "LOINC",
            "6598-7",
        ),
        (
            r"\b(?:serum\s+)?potassium\s*(?:was|of|=|:)?\s*(\d+(?:\.\d+)?)\s*(?:mmol/L|mEq/L)",
            "Potassium",
            "LOINC",
            "2823-3",
        ),
        (
            r"\btemperature\s*(?:was|of|=|:)?\s*(\d+(?:\.\d+)?)\s*(?:°C|C)",
            "Temperature",
            "LOINC",
            "8310-5",
        ),
        (
            r"\bblood pressure\s*(?:was|of|=|:)?\s*(\d{2,3}/\d{2,3})\s*mmHg",
            "Blood pressure",
            "LOINC",
            "85354-9",
        ),
        (
            r"\bFEV1/FVC\s*(?:was|=|:)?\s*(0?\.\d+)",
            "FEV1/FVC",
            "LOINC",
            "19926-5",
        ),
        (
            r"\bFEV1\s*(?:was|=|:)?\s*(\d+(?:\.\d+)?)\s*%",
            "FEV1",
            "LOINC",
            "20150-9",
        ),
        (
            r"\bFVC\s*(?:was|=|:)?\s*(\d+(?:\.\d+)?)\s*%",
            "FVC",
            "LOINC",
            "19870-5",
        ),
        (
            r"\bFENa\s*(?:was|=|:)?\s*(\d+(?:\.\d+)?)\s*%",
            "Fractional excretion of sodium",
            "LOINC",
            "29701-7",
        ),
    ]

    @staticmethod
    def _evidence(text: str, start: int, end: int) -> str:
        """Return a useful source window around the extracted value."""
        left = max(0, start - 80)
        right = min(len(text), end + 120)
        return text[left:right].strip()

    @staticmethod
    def _confidence(entity_type: str) -> float:
        """Confidence is intentionally conservative for deterministic matching."""
        return {
            "diagnosis": 0.90,
            "medication": 0.96,
            "symptom": 0.94,
            "procedure": 0.95,
            "lab": 0.93,
        }.get(entity_type, 0.90)

    def _add_term_entities(
        self,
        text: str,
        entities: list[ExtractedEntityData],
        terms: dict,
        entity_type: str,
    ) -> None:
        lower = text.lower()

        # Longer terms first prevents partial matches such as
        # "angina" inside "exertional angina".
        for term in sorted(terms, key=len, reverse=True):
            pattern = re.compile(
                rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])",
                re.IGNORECASE,
            )

            for match in pattern.finditer(lower):
                normalized, code, code_system = terms[term]

                # Avoid duplicate overlapping entities.
                overlap = any(
                    existing["start_offset"] < match.end()
                    and existing["end_offset"] > match.start()
                    and existing["type"] == entity_type
                    for existing in entities
                )

                if overlap:
                    continue

                raw = text[match.start():match.end()]

                entities.append(
                    {
                        "type": entity_type,
                        "raw_text": raw,
                        "normalized_value": normalized,
                        "code": code or None,
                        "code_system": code_system or None,
                        "confidence": self._confidence(entity_type),
                        "assertion": detect_assertion(
                            text, match.start(), match.end(), detect_section(text, match.start())
                        ).value,
                        "section": detect_section(text, match.start()),
                        "evidence_text": raw,
                        "start_offset": match.start(),
                        "end_offset": match.end(),
                        "page_number": 1,
                        "details": self._medication_details(text, match.start(), match.end())
                        if entity_type == "medication" else {},
                    }
                )

    def _add_lab_entities(
        self,
        text: str,
        entities: list[ExtractedEntityData],
    ) -> None:
        for pattern, name, code_system, code in self.LAB_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                value = match.group(1)
                raw = match.group(0)

                entities.append(
                    {
                        "type": "lab",
                        "raw_text": raw,
                        "normalized_value": f"{name}: {value}",
                        "code": code or None,
                        "code_system": code_system,
                        "confidence": self._confidence("lab"),
                        "assertion": detect_assertion(
                            text, match.start(), match.end(), detect_section(text, match.start())
                        ).value,
                        "section": detect_section(text, match.start()),
                        "evidence_text": raw,
                        "start_offset": match.start(),
                        "end_offset": match.end(),
                        "page_number": 1,
                    }
                )

    async def extract_clinical_entities(
        self,
        text: str,
    ) -> ExtractionResult:
        entities: list[ExtractedEntityData] = []

        if not text or not text.strip():
            return ExtractionResult(
                entities=[],
                model_name="local-clinical-extractor",
                model_version="v1.0",
                raw_response={
                    "status": "empty_input",
                    "entity_count": 0,
                },
            )

        self._add_term_entities(
            text,
            entities,
            self.DIAGNOSES,
            "diagnosis",
        )

        self._add_term_entities(
            text,
            entities,
            self.MEDICATIONS,
            "medication",
        )

        self._add_term_entities(
            text,
            entities,
            self.SYMPTOMS,
            "symptom",
        )

        self._add_term_entities(
            text,
            entities,
            self.PROCEDURES,
            "procedure",
        )

        self._add_lab_entities(text, entities)

        # Stable ordering by source position.
        entities.sort(
            key=lambda entity: (
                entity["start_offset"],
                entity["end_offset"],
            )
        )

        return ExtractionResult(
            entities=entities,
            model_name="local-clinical-extractor",
            model_version="v1.0",
            raw_response={
                "status": "success",
                "provider": "local",
                "entity_count": len(entities),
            },
        )
