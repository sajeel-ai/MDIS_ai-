"""Run the deterministic local extractor against synthetic labeled fixtures."""

import argparse
import asyncio
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from app.providers.extraction.local import LocalExtractionProvider


EVAL_DIR = Path(__file__).resolve().parents[2] / "evals"
FIXTURES_PATH = EVAL_DIR / "fixtures.json"
LATEST_PATH = EVAL_DIR / "latest_eval.json"
BASELINE_PATH = EVAL_DIR / "baseline.json"
ENTITY_TYPES = ("diagnosis", "medication", "symptom", "procedure", "lab")


async def evaluate() -> dict:
    fixtures = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    provider = LocalExtractionProvider()
    counts = {entity_type: Counter() for entity_type in ENTITY_TYPES}
    assertion_total = assertion_correct = 0

    for fixture in fixtures:
        output = await provider.extract_clinical_entities(fixture["text"])
        expected = defaultdict(list)
        actual = defaultdict(list)
        for entity in fixture["entities"]:
            expected[(entity["type"], entity["normalized_value"])].append(entity["assertion"])
        for entity in output["entities"]:
            actual[(entity["type"], entity["normalized_value"])].append(entity["assertion"])

        for key in set(expected) | set(actual):
            entity_type = key[0]
            if entity_type not in counts:
                continue
            matched = min(len(expected[key]), len(actual[key]))
            counts[entity_type]["tp"] += matched
            counts[entity_type]["fp"] += len(actual[key]) - matched
            counts[entity_type]["fn"] += len(expected[key]) - matched
            for gold_assertion, predicted_assertion in zip(expected[key], actual[key]):
                assertion_total += 1
                assertion_correct += gold_assertion == predicted_assertion

    precision_by_type = {}
    recall_by_type = {}
    f1_by_type = {}
    for entity_type, values in counts.items():
        tp, fp, fn = values["tp"], values["fp"], values["fn"]
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        precision_by_type[entity_type] = round(precision, 4)
        recall_by_type[entity_type] = round(recall, 4)
        f1_by_type[entity_type] = round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0

    return {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "fixtures_evaluated": len(fixtures),
        "precision_by_type": precision_by_type,
        "recall_by_type": recall_by_type,
        "f1_by_type": f1_by_type,
        "assertion_accuracy": round(assertion_correct / assertion_total, 4) if assertion_total else 0.0,
        "assertion_entities_evaluated": assertion_total,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-baseline", action="store_true")
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()
    report = asyncio.run(evaluate())
    LATEST_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if args.update_baseline:
        BASELINE_PATH.write_text(json.dumps({"f1_by_type": report["f1_by_type"]}, indent=2) + "\n", encoding="utf-8")
    elif args.check_baseline:
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        drops = {
            name: (baseline["f1_by_type"][name], value)
            for name, value in report["f1_by_type"].items()
            if value < baseline["f1_by_type"].get(name, 0.0)
        }
        if drops:
            print(json.dumps({"baseline_f1_drops": drops}, indent=2))
            return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
