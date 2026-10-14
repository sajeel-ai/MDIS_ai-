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
        "htn": ("Hypertension", "I10", "ICD10"),
        "diabetes mellitus": ("Diabetes mellitus", "", ""),
        "diabetes": ("Diabetes mellitus", "", ""),
        "acute copd exacerbation": (
            "Acute exacerbation of chronic obstructive pulmonary disease",
            "J44.1",
            "ICD10",
        ),
        "copd": ("Chronic obstructive pulmonary disease", "J44.9", "ICD10"),
        "chronic obstructive pulmonary disease": (
            "Chronic obstructive pulmonary disease",
            "J44.9",
            "ICD10",
        ),
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
        r"(?:at\s+bedtime|every\s+night|nightly|q\.?\s*h\.?s\.?)|"
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
        details: dict[str, str] = {}
        dose = cls._DOSE_PATTERN.search(after_window)
        if dose:
            details["dose"] = f"{dose.group(1)} {dose.group(2)}"
        frequency = cls._FREQUENCY_PATTERN.search(after_window)
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

    VITAL_PATTERNS = [
        (r"\b(?:blood\s+pressure|b\s*/\s*p|bp)\s*(?:was|is|:|=)?\s*(\d{2,3})\s*(?:/|over)\s*(\d{2,3})\s*(mmhg)?", "Blood pressure", "85354-9", "blood_pressure"),
        (r"(?<![\d/])\b(\d{2,3})\s*/\s*(\d{2,3})\s*mmhg\b", "Blood pressure", "85354-9", "blood_pressure"),
        (r"\b(?:heart\s+rate|hr)\s*(?:was|is|:|=)?\s*(\d{2,3})\s*(bpm)?", "Heart rate", "8867-4", "heart_rate"),
        (r"\b(?:respiratory\s+rate|respirations?|rr)\s*(?:was|is|:|=)?\s*(\d{1,2})\s*(?:breaths?/min|rpm)?", "Respiratory rate", "9279-1", "respiratory_rate"),
        (r"\b(?:temperature|temp|t)\s*(?:was|is|:|=)?\s*(\d{2,3}(?:\.\d+)?)\s*(°?\s*[cf])\b", "Body temperature", "8290-1", "temperature"),
        (r"\b(?:spo2|oxygen\s+saturation|o2\s+sat(?:uration)?)\s*(?:was|is|:|=)?\s*(\d{2,3})\s*%?\s*(ra|room\s+air)?", "Oxygen saturation", "59408-5", "spo2"),
        (r"\b(?:weight|wt)\s*(?:was|is|:|=)?\s*(\d+(?:\.\d+)?)\s*(kg|lb|lbs?)\b", "Body weight", "29463-7", "weight"),
        (r"\b(?:height|ht)\s*(?:was|is|:|=)?\s*(\d+(?:\.\d+)?)\s*(cm|m|in|ft)\b", "Body height", "8302-2", "height"),
        (r"\b(?:bmi|body\s+mass\s+index)\s*(?:was|is|:|=)?\s*(\d+(?:\.\d+)?)\b", "Body mass index", "39156-5", "bmi"),
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

    @staticmethod
    def _is_finding_assertion(assertion: str) -> bool:
        return assertion != "hypothetical"

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
                assertion = detect_assertion(
                    text, match.start(), match.end(), detect_section(text, match.start())
                ).value
                if not self._is_finding_assertion(assertion):
                    continue

                entities.append(
                    {
                        "type": entity_type,
                        "raw_text": raw,
                        "normalized_value": normalized,
                        "code": code or None,
                        "code_system": code_system or None,
                        "confidence": self._confidence(entity_type),
                        "assertion": assertion,
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

        row_pattern = re.compile(r"(?im)^(?P<name>[A-Za-z][A-Za-z0-9 /()_-]{2,40})(?:\s*[:|]\s*|\s{2,})(?P<value>[-+]?\d+(?:\.\d+)?)\s*$")
        for match in row_pattern.finditer(text):
            name, raw = match.group("name").strip(), match.group(0).strip()
            if re.search(r"\b(?:blood pressure|bp|heart rate|hr|respiratory rate|rr|temperature|temp|spo2|weight|height|bmi)\b", name, re.I):
                continue
            if any(e["type"] == "lab" and e["start_offset"] < match.end() and e["end_offset"] > match.start() for e in entities):
                continue
            entities.append({"type": "lab", "raw_text": raw, "normalized_value": name, "code": None, "code_system": None, "confidence": 0.65, "assertion": "present", "section": detect_section(text, match.start()), "evidence_text": raw, "start_offset": match.start(), "end_offset": match.end(), "page_number": 1, "details": {"test_name": name, "value": match.group("value"), "unit": None, "reference_range": None, "flag": None, "validation_warnings": ["incomplete_lab_row"]}})

    def _add_pain_entities(self, text: str, entities: list[ExtractedEntityData]) -> None:
        patterns = [
            re.compile(r"\b((?:(?P<severity>mild|moderate|severe)\s+)?(?:(?P<laterality>right|left|bilateral)\s+)?(?P<site>(?:upper|lower)\s+quadrant|(?:lower\s+)?back|chest|abdominal|abdomen|knee|throat|head|neck|shoulder|leg|arm|pelvic)\s+pain)\b", re.I),
            re.compile(r"\bpain\s+in\s+(?:the\s+)?(?:(?P<laterality>right|left|bilateral)\s+)?(?P<site>knee|shoulder|hip|arm|leg|throat|quadrant)\b", re.I),
        ]
        spans: list[tuple[int, int, str]] = []
        for pattern in patterns:
            for match in pattern.finditer(text):
                spans.append((match.start(), match.end(), match.group(0)))
        coordinated = re.compile(r"\b(?P<first>chest|abdominal|back|head|throat)\s+and\s+(?P<second>chest|abdominal|back|head|throat)\s+pain\b", re.I)
        for match in coordinated.finditer(text):
            for group in ("first", "second"):
                start = match.start(group)
                spans.append((start, start + len(match.group(group)) + 5, match.group(group) + " pain"))
        for start, end, raw in sorted(spans):
            if any(e["type"] == "symptom" and e["start_offset"] < end and e["end_offset"] > start for e in entities):
                continue
            lower = raw.lower()
            site = re.sub(r"^(?:mild|moderate|severe)\s+", "", lower)
            site = re.sub(r"^(?:right|left|bilateral)\s+", "", site).removesuffix(" pain")
            if lower.startswith("pain in "):
                site_match = re.search(r"\b(?:right|left|bilateral)\s+(?P<site>[a-z ]+)$", lower)
                if site_match:
                    site = site_match.group("site").strip()
                else:
                    site = re.sub(r"^pain\s+in\s+(?:the\s+)?", "", lower).strip()
            normalized_site = "back" if site == "lower back" else "abdominal" if site in {"abdomen", "upper quadrant", "lower quadrant"} else site
            assertion = detect_assertion(text, start, end, detect_section(text, start)).value
            if not self._is_finding_assertion(assertion):
                continue
            details = {"site": site}
            for key, values in (("severity", ("mild", "moderate", "severe")), ("laterality", ("right", "left", "bilateral"))):
                found = next((value for value in values if re.search(rf"\b{value}\b", lower)), None)
                if found:
                    details[key] = found
            entities.append({"type": "symptom", "raw_text": raw, "normalized_value": normalized_site[:1].upper() + normalized_site[1:] + " pain", "code": None, "code_system": None, "confidence": self._confidence("symptom"), "assertion": assertion, "section": detect_section(text, start), "evidence_text": raw, "start_offset": start, "end_offset": end, "page_number": 1, "details": details})

    def _add_vital_entities(self, text: str, entities: list[ExtractedEntityData]) -> None:
        for pattern, name, code, vital_key in self.VITAL_PATTERNS:
            for match in re.finditer(pattern, text, re.I):
                if any(e["type"] == "vital" and e["start_offset"] < match.end() and e["end_offset"] > match.start() for e in entities):
                    continue
                groups = match.groups()
                details: dict[str, object] = {"vital_sign": vital_key, "loinc": code, "raw_unit": None}
                if vital_key == "blood_pressure":
                    try:
                        systolic, diastolic = int(groups[0]), int(groups[1])
                    except (IndexError, TypeError, ValueError):
                        continue
                    unit = groups[2] if len(groups) > 2 else None
                    details.update({"systolic": systolic, "diastolic": diastolic, "unit": (unit or "mmHg").strip()})
                    details["validation_warnings"] = ["implausible_blood_pressure"] if systolic <= diastolic or not 50 <= systolic <= 300 or not 20 <= diastolic <= 200 else []
                elif vital_key == "temperature":
                    try:
                        details.update({"value": float(groups[0]), "unit": re.sub(r"\s+", "", groups[1]).upper()})
                    except (IndexError, TypeError, ValueError):
                        continue
                elif vital_key == "spo2": details.update({"value": float(groups[0]), "unit": "%", "on_room_air": bool(groups[1])})
                elif vital_key in {"heart_rate", "respiratory_rate"}: details.update({"value": float(groups[0]), "unit": ((groups[1] if len(groups) > 1 else None) or ("bpm" if vital_key == "heart_rate" else "breaths/min")).strip()})
                elif vital_key in {"weight", "height"}:
                    try:
                        details.update({"value": float(groups[0]), "unit": groups[1] if len(groups) > 1 else None})
                    except (IndexError, TypeError, ValueError):
                        continue
                else:
                    try:
                        details.update({"value": float(groups[0]), "unit": None})
                    except (IndexError, TypeError, ValueError):
                        continue
                entities.append({"type": "vital", "raw_text": match.group(0), "normalized_value": name, "code": code, "code_system": "LOINC", "confidence": 0.96, "assertion": "present", "section": detect_section(text, match.start()), "evidence_text": match.group(0), "start_offset": match.start(), "end_offset": match.end(), "page_number": 1, "details": details})

        # Handle common pipe/tab tables without assuming a fixed column count.
        table_specs = {
            "blood pressure": ("Blood pressure", "85354-9", "blood_pressure"),
            "bp": ("Blood pressure", "85354-9", "blood_pressure"),
            "b/p": ("Blood pressure", "85354-9", "blood_pressure"),
            "heart rate": ("Heart rate", "8867-4", "heart_rate"),
            "hr": ("Heart rate", "8867-4", "heart_rate"),
            "respiratory rate": ("Respiratory rate", "9279-1", "respiratory_rate"),
            "rr": ("Respiratory rate", "9279-1", "respiratory_rate"),
            "temperature": ("Body temperature", "8290-1", "temperature"),
            "temp": ("Body temperature", "8290-1", "temperature"),
            "spo2": ("Oxygen saturation", "59408-5", "spo2"),
            "oxygen saturation": ("Oxygen saturation", "59408-5", "spo2"),
            "weight": ("Body weight", "29463-7", "weight"),
            "height": ("Body height", "8302-2", "height"),
            "bmi": ("Body mass index", "39156-5", "bmi"),
        }
        cursor = 0
        for line in text.splitlines(keepends=True):
            raw_line = line.rstrip("\r\n")
            start = cursor
            cursor += len(line)
            columns = [part.strip() for part in re.split(r"[|\t]", raw_line)]
            if len(columns) < 2:
                continue
            spec = table_specs.get(columns[0].casefold())
            if spec is None:
                continue
            name, code, vital_key = spec
            if any(e["type"] == "vital" and e["start_offset"] < start + len(raw_line) and e["end_offset"] > start for e in entities):
                continue
            numbers = re.findall(r"[-+]?\d+(?:\.\d+)?", " ".join(columns[1:]))
            if not numbers:
                continue
            details: dict[str, object] = {"vital_sign": vital_key, "loinc": code, "raw_unit": None}
            unit = next((part for part in columns[1:] if re.fullmatch(r"(?:mmhg|bpm|rpm|kg|lb|lbs?|cm|m|in|ft|c|f|%)", part, re.I)), None)
            warnings: list[str] = []
            try:
                if vital_key == "blood_pressure" and len(numbers) >= 2:
                    systolic, diastolic = int(float(numbers[0])), int(float(numbers[1]))
                    details.update({"systolic": systolic, "diastolic": diastolic, "unit": unit or "mmHg"})
                    if systolic <= diastolic or not 50 <= systolic <= 300 or not 20 <= diastolic <= 200:
                        warnings.append("implausible_blood_pressure")
                else:
                    details.update({"value": float(numbers[0]), "unit": unit})
                if unit is None and vital_key not in {"bmi", "blood_pressure"}:
                    warnings.append("missing_vital_unit")
            except (TypeError, ValueError):
                warnings.append("malformed_vital_value")
            if warnings:
                details["validation_warnings"] = warnings
            entities.append({"type": "vital", "raw_text": raw_line, "normalized_value": name, "code": code, "code_system": "LOINC", "confidence": 0.9, "assertion": "present", "section": detect_section(text, start), "evidence_text": raw_line, "start_offset": start, "end_offset": start + len(raw_line), "page_number": 1, "details": details})

        aligned_specs = {key: value for key, value in table_specs.items()}
        offset = 0
        for line in text.splitlines(keepends=True):
            raw_line = line.rstrip("\r\n")
            start = offset
            offset += len(line)
            match = re.match(r"^\s*(Blood Pressure|BP|B/P|Heart Rate|HR|Respiratory Rate|RR|Temperature|Temp|SpO2|Oxygen Saturation|Weight|Height|BMI)\s{2,}(.+?)\s*$", raw_line, re.I)
            if not match:
                continue
            spec = aligned_specs.get(match.group(1).casefold())
            if spec is None:
                continue
            name, code, vital_key = spec
            numbers = re.findall(r"[-+]?\d+(?:\.\d+)?", match.group(2))
            if not numbers or any(e["type"] == "vital" and e["start_offset"] < start + len(raw_line) and e["end_offset"] > start for e in entities):
                continue
            unit = next((part for part in match.group(2).split() if re.fullmatch(r"(?:mmhg|bpm|rpm|kg|lb|lbs?|cm|m|in|ft|c|f|%)", part, re.I)), None)
            details: dict[str, object] = {"vital_sign": vital_key, "loinc": code, "raw_unit": None}
            warnings: list[str] = []
            try:
                if vital_key == "blood_pressure" and len(numbers) >= 2:
                    details.update({"systolic": int(float(numbers[0])), "diastolic": int(float(numbers[1])), "unit": unit or "mmHg"})
                else:
                    details.update({"value": float(numbers[0]), "unit": unit})
                if unit is None and vital_key not in {"blood_pressure", "bmi"}:
                    warnings.append("missing_vital_unit")
            except (TypeError, ValueError):
                warnings.append("malformed_vital_value")
            if warnings:
                details["validation_warnings"] = warnings
            entities.append({"type": "vital", "raw_text": raw_line, "normalized_value": name, "code": code, "code_system": "LOINC", "confidence": 0.9, "assertion": "present", "section": detect_section(text, start), "evidence_text": raw_line, "start_offset": start, "end_offset": start + len(raw_line), "page_number": 1, "details": details})

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
        self._add_pain_entities(text, entities)

        self._add_term_entities(
            text,
            entities,
            self.PROCEDURES,
            "procedure",
        )

        self._add_vital_entities(text, entities)
        self._add_lab_entities(text, entities)
        self._merge_entities(entities)

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

    @staticmethod
    def _merge_entities(entities: list[ExtractedEntityData]) -> None:
        groups: dict[tuple[str, str, str], list[ExtractedEntityData]] = {}
        for entity in entities:
            key = (entity["type"], re.sub(r"\s+", " ", entity["normalized_value"].strip().lower()), entity.get("assertion", "present"))
            groups.setdefault(key, []).append(entity)
        for group in groups.values():
            if len(group) > 1:
                if group[0]["type"] == "vital":
                    continue
                if group[0]["type"] == "symptom":
                    modifier_keys = ("site", "severity", "laterality")
                    signatures = {
                        tuple(item.get("details", {}).get(key) for key in modifier_keys)
                        for item in group
                    }
                    if len(signatures) > 1:
                        continue
                group[0].setdefault("details", {})["evidence_spans"] = [{"text": x["evidence_text"], "start_offset": x["start_offset"], "end_offset": x["end_offset"]} for x in group]
                for duplicate in group[1:]:
                    entities.remove(duplicate)
        concepts: dict[tuple[str, str], list[ExtractedEntityData]] = {}
        for entity in entities:
            key = (entity["type"], re.sub(r"\s+", " ", entity["normalized_value"].strip().lower()))
            concepts.setdefault(key, []).append(entity)
        for group in concepts.values():
            if len(group) > 1 and len({x.get("assertion", "present") for x in group}) > 1:
                for entity in group:
                    entity.setdefault("details", {})["assertion_conflict"] = True
