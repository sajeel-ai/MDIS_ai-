"""Baseline scoring harness for the synthetic MDIS fixture pack.

This tool deliberately does not alter extraction behavior.  It runs the real
local OCR and extraction providers, then reports strict and lenient matching.
DOC-006 is scored automatically once its ground-truth entry is present.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

# Make the harness runnable as ``python tools/score_mdis_fixtures.py`` from
# the backend directory without requiring an installed package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.providers.extraction.local import LocalExtractionProvider
from app.providers.ocr.local import LocalOCRProvider


ASSERTION_ALIASES = {
    "absent": "negated",
    "negated": "negated",
    "present": "present",
}

FREQUENCY_ALIASES = {
    "bid": "twice daily",
    "bd": "twice daily",
    "twice daily": "twice daily",
    "od": "once daily",
    "qd": "once daily",
    "once daily": "once daily",
    "q8h prn": "every 8 hours as needed",
    "every 8 hours as needed": "every 8 hours as needed",
    "prn": "as needed",
    "as needed": "as needed",
}

ROUTE_ALIASES = {"po": "oral", "oral": "oral"}


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def concept(value: Any) -> str:
    value = clean(value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def assertion(value: Any) -> str:
    return ASSERTION_ALIASES.get(clean(value), clean(value))


def frequency(value: Any) -> str:
    value = clean(value)
    return FREQUENCY_ALIASES.get(value, value)


def route(value: Any) -> str:
    value = clean(value)
    return ROUTE_ALIASES.get(value, value)


def expected_code(entity: dict[str, Any]) -> tuple[str, str] | None:
    for field, system in (("snomed", "SNOMED"), ("icd10", "ICD10"), ("rxnorm", "RxNorm"), ("loinc", "LOINC")):
        if entity.get(field):
            return system, str(entity[field])
    return None


def expected_codes(entity: dict[str, Any]) -> list[tuple[str, str]]:
    fields = (("snomed", "SNOMED"), ("icd10", "ICD10"), ("rxnorm", "RxNorm"), ("loinc", "LOINC"))
    return [(system, str(entity[field])) for field, system in fields if entity.get(field)]


def predicted_code(entity: dict[str, Any]) -> tuple[str, str] | None:
    if entity.get("code") and entity.get("code_system"):
        return clean(entity["code_system"]), str(entity["code"])
    return None


def same_type(expected: dict[str, Any], predicted: dict[str, Any]) -> bool:
    return clean(expected.get("type")) == clean(predicted.get("type"))


def strict_concept_match(expected: dict[str, Any], predicted: dict[str, Any]) -> bool:
    return same_type(expected, predicted) and concept(expected.get("normalized")) == concept(predicted.get("normalized_value"))


def lenient_concept_match(expected: dict[str, Any], predicted: dict[str, Any]) -> bool:
    if not same_type(expected, predicted):
        return False
    left = set(concept(expected.get("normalized")).split())
    right = set(concept(predicted.get("normalized_value")).split())
    return bool(left and right and (left <= right or right <= left or left & right))


def empty_metrics() -> dict[str, int | float | str]:
    return {"tp": 0, "fp": 0, "fn": 0, "precision": "n/a", "recall": "n/a", "f1": "n/a"}


def metrics(tp: int, fp: int, fn: int) -> dict[str, int | float | str]:
    if not tp and not fp and not fn:
        return empty_metrics()
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3)}


def match_entities(expected: list[dict[str, Any]], predicted: list[dict[str, Any]], matcher) -> tuple[list[tuple[dict, dict]], list[dict], list[dict]]:
    used: set[int] = set()
    matches: list[tuple[dict, dict]] = []
    missed: list[dict] = []
    for item in expected:
        found = next(((index, candidate) for index, candidate in enumerate(predicted) if index not in used and matcher(item, candidate)), None)
        if found is None:
            missed.append(item)
        else:
            used.add(found[0])
            matches.append((item, found[1]))
    return matches, missed, [item for index, item in enumerate(predicted) if index not in used]


def classify_extras(expected: list[dict[str, Any]], extras: list[dict[str, Any]], matched: list[tuple[dict, dict]]) -> list[dict[str, Any]]:
    result = []
    matched_predicted = [predicted for _, predicted in matched]
    seen: list[dict[str, Any]] = []
    def same_predicted(left: dict[str, Any], right: dict[str, Any]) -> bool:
        return clean(left.get("type")) == clean(right.get("type")) and concept(left.get("normalized_value")) == concept(right.get("normalized_value"))
    for extra in extras:
        if any(same_predicted(previous, extra) for previous in matched_predicted) or any(same_predicted(previous, extra) for previous in seen):
            kind = "duplicate"
        elif any(lenient_concept_match(item, extra) for item in expected):
            kind = "wording_variant"
        else:
            kind = "true_false_positive"
        result.append({"classification": kind, "entity": extra})
        seen.append(extra)
    return result


def code_matches(expected: dict[str, Any], predicted: dict[str, Any]) -> tuple[bool, str]:
    wanted = expected_code(expected)
    actual = predicted_code(predicted)
    if wanted is None:
        return True, "not_expected"
    if actual is None or clean(wanted[0]) != clean(actual[0]):
        return False, "system_mismatch"
    if wanted[1] == actual[1]:
        return True, "exact"
    # RxNorm may use an ingredient or a clinical-drug/product code.  The
    # normalized concept is the offline equivalence signal; no external
    # terminology lookup is performed by this baseline harness.
    if clean(wanted[0]) == "rxnorm" and strict_concept_match(expected, predicted):
        return True, "rxnorm_concept_equivalent"
    return False, "code_mismatch"


async def score(pack: Path) -> dict[str, Any]:
    ground_truth = json.loads((pack / "ground_truth.json").read_text(encoding="utf-8"))
    truth_by_id = {item["document_id"]: item for item in ground_truth["documents"]}
    ocr = LocalOCRProvider()
    extractor = LocalExtractionProvider()
    categories = ("diagnosis", "symptom", "medication", "lab", "vital", "allergy")
    overall = {category: {"strict": [0, 0, 0], "lenient": [0, 0, 0]} for category in categories}
    assertion_totals = [0, 0]
    code_totals = [0, 0]
    any_system_code_totals = [0, 0]
    code_by_system: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    dangerous_errors: list[dict[str, Any]] = []
    output: dict[str, Any] = {"ground_truth_documents": sorted(truth_by_id), "unscored_documents": [], "documents": {}}

    for path in sorted((pack / "documents").glob("*.pdf")):
        document_id = path.name.split("_", 1)[0]
        if document_id not in truth_by_id:
            output["unscored_documents"].append({"document_id": document_id, "file": str(path)})
            continue
        truth = truth_by_id[document_id]
        ocr_result = await ocr.extract_text(path.read_bytes(), "application/pdf")
        predicted = (await extractor.extract_clinical_entities(ocr_result["text"]))["entities"]
        strict_matches, strict_missed, strict_extra = match_entities(truth["entities"], predicted, strict_concept_match)
        lenient_matches, lenient_missed, lenient_extra = match_entities(truth["entities"], predicted, lenient_concept_match)
        strict_by_category = defaultdict(lambda: [0, 0, 0])
        lenient_by_category = defaultdict(lambda: [0, 0, 0])
        for item, _ in strict_matches: strict_by_category[item["type"]][0] += 1
        for item in strict_missed: strict_by_category[item["type"]][2] += 1
        for item in strict_extra: strict_by_category[item.get("type", "unknown")][1] += 1
        for item, _ in lenient_matches: lenient_by_category[item["type"]][0] += 1
        for item in lenient_missed: lenient_by_category[item["type"]][2] += 1
        for item in lenient_extra: lenient_by_category[item.get("type", "unknown")][1] += 1
        for category in categories:
            for mode, values in (("strict", strict_by_category[category]), ("lenient", lenient_by_category[category])):
                for index in range(3): overall[category][mode][index] += values[index]
        assertion_total = assertion_correct = code_total = code_correct = 0
        wrong = []
        for expected, actual in lenient_matches:
            assertion_total += 1
            assertion_ok = assertion(expected["assertion"]) == assertion(actual.get("assertion"))
            assertion_correct += assertion_ok
            assertion_totals[0] += assertion_ok
            assertion_totals[1] += 1
            codes = expected_codes(expected)
            if codes:
                predicted = predicted_code(actual)
                any_code_ok = False
                for system, value in codes:
                    code_total += 1
                    code_ok = bool(predicted and clean(predicted[0]) == clean(system) and (predicted[1] == value or (system == "RxNorm" and strict_concept_match(expected, actual))))
                    code_correct += code_ok
                    code_totals[0] += code_ok
                    code_totals[1] += 1
                    code_by_system[system][0] += code_ok
                    code_by_system[system][1] += 1
                    any_code_ok = any_code_ok or code_ok
                any_system_code_totals[0] += any_code_ok
                any_system_code_totals[1] += 1
            expected_assertion = assertion(expected["assertion"])
            actual_assertion = assertion(actual.get("assertion"))
            if expected_assertion in {"negated", "family", "possible", "discontinued"} and actual_assertion == "present":
                dangerous_errors.append({"kind": "assertion_as_present", "document_id": document_id, "text": expected.get("text"), "expected": expected_assertion, "actual": actual_assertion})
            if expected_assertion == "discontinued" and actual_assertion != "discontinued":
                dangerous_errors.append({"kind": "discontinued_as_current", "document_id": document_id, "text": expected.get("text"), "expected": expected_assertion, "actual": actual_assertion})
            if expected_assertion == "family" and actual_assertion == "present":
                dangerous_errors.append({"kind": "family_assigned_patient", "document_id": document_id, "text": expected.get("text"), "expected": expected_assertion, "actual": actual_assertion})
            if expected_assertion == "negated" and actual_assertion == "historical":
                dangerous_errors.append({"kind": "negation_as_historical", "document_id": document_id, "text": expected.get("text"), "expected": expected_assertion, "actual": actual_assertion})
            differences = {}
            if assertion(expected["assertion"]) != assertion(actual.get("assertion")):
                differences["assertion"] = {"expected": assertion(expected["assertion"]), "actual": assertion(actual.get("assertion"))}
            for field, normalizer in (("frequency", frequency), ("route", route)):
                expected_value = expected.get(field)
                actual_value = actual.get("details", {}).get(field)
                if expected_value and normalizer(expected_value) != normalizer(actual_value):
                    differences[field] = {"expected": normalizer(expected_value), "actual": normalizer(actual_value)}
            if expected.get("type") == "medication" and frequency(expected.get("frequency")) == "at bedtime" and frequency(actual.get("details", {}).get("frequency")) == "twice daily":
                dangerous_errors.append({"kind": "bedtime_as_twice_daily", "document_id": document_id, "text": expected.get("text"), "expected": "at bedtime", "actual": "twice daily"})
            if codes and not all(
                predicted_code(actual)
                and clean(predicted_code(actual)[0]) == clean(system)
                and (predicted_code(actual)[1] == value or (system == "RxNorm" and strict_concept_match(expected, actual)))
                for system, value in codes
            ):
                differences["code"] = {"expected": codes, "actual": predicted_code(actual)}
            if differences:
                wrong.append({"expected": expected, "predicted": actual, "differences": differences})
        output["documents"][document_id] = {
            "engine": ocr_result["engine"],
            "pages": ocr_result["page_count"],
            "methods": [page.get("method") for page in ocr_result["pages"]],
            "strict": {category: metrics(*strict_by_category[category]) for category in categories},
            "lenient": {category: metrics(*lenient_by_category[category]) for category in categories},
            "assertion_accuracy": [assertion_correct, assertion_total],
            "code_accuracy": [code_correct, code_total],
            "missed": strict_missed,
            "wrong": wrong,
            "extra": classify_extras(truth["entities"], strict_extra, strict_matches),
        }
    output["overall"] = {mode: {category: metrics(*values[mode]) for category, values in overall.items()} for mode in ("strict", "lenient")}
    output["assertion_accuracy"] = {"correct": assertion_totals[0], "total": assertion_totals[1]}
    output["code_accuracy"] = {"correct": code_totals[0], "total": code_totals[1], "by_system": {system: {"correct": values[0], "total": values[1]} for system, values in sorted(code_by_system.items())}, "has_correct_code_any_system": {"correct": any_system_code_totals[0], "total": any_system_code_totals[1]}}
    # Report each underlying dangerous mismatch once even if it triggers more
    # than one rule (for example a discontinued drug also counted as present).
    unique_dangerous = list({(item["document_id"], item["text"], item["expected"], item["actual"]): item for item in dangerous_errors}.values())
    output["dangerous_errors"] = unique_dangerous
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", type=Path, default=Path(__file__).parents[1] / "tests" / "fixtures" / "mdis-test-pack")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(score(args.pack))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
