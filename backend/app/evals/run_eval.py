"""Evaluation Harness for MDIS Clinical Extraction and OCR Quality.

Evaluates clinical entity extraction (precision, recall, F1 per entity type and per document category),
assertion accuracy (negation, temporality), character error rate (CER), word error rate (WER),
and bounding box IoU.
"""

import argparse
import asyncio
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

from app.evals.loader import load_dataset
from app.evals.ocr_metrics import bbox_iou, cer, wer
from app.providers.extraction.local import LocalExtractionProvider


EVAL_DIR = Path(__file__).resolve().parents[2] / "evals"
FIXTURES_PATH = EVAL_DIR / "fixtures.json"
LATEST_PATH = EVAL_DIR / "latest_eval.json"
BASELINE_PATH = EVAL_DIR / "baseline.json"
BASELINE_HASH_PATH = EVAL_DIR / "baseline.sha256"
ENTITY_TYPES = ("diagnosis", "medication", "symptom", "procedure", "lab")


def _compute_prf(counts_dict: dict) -> tuple[dict, dict, dict]:
    """Compute precision, recall, and F1 from TP, FP, FN counters."""
    precision_out = {}
    recall_out = {}
    f1_out = {}
    for key, values in counts_dict.items():
        tp = values["tp"]
        fp = values["fp"]
        fn = values["fn"]
        p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * p * r) / (p + r) if (p + r) > 0 else 0.0
        precision_out[key] = round(p, 4)
        recall_out[key] = round(r, 4)
        f1_out[key] = round(f1, 4)
    return precision_out, recall_out, f1_out


def baseline_digest(path: Path = BASELINE_PATH) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_baseline_integrity(path: Path = BASELINE_PATH, hash_path: Path | None = None) -> None:
    """Reject an edited or unsealed baseline before using it for regression checks."""
    sidecar = hash_path or path.with_suffix(".sha256")
    if not path.is_file() or not sidecar.is_file():
        raise ValueError(f"Baseline integrity record is missing for {path}")
    expected = sidecar.read_text(encoding="ascii").strip().split()[0]
    if not expected or baseline_digest(path) != expected:
        raise ValueError(f"Baseline integrity check failed; regenerate it with --update-baseline: {path}")


def write_baseline(report: dict, path: Path = BASELINE_PATH, hash_path: Path | None = None) -> None:
    baseline_data = {
        "generated_at": report["measured_at"],
        "f1_by_type": report["f1_by_type"],
        "f1_by_category": report["f1_by_category"],
        "assertion_accuracy": report["assertion_accuracy"],
        "mean_cer": report["mean_cer"],
        "mean_wer": report["mean_wer"],
    }
    path.write_text(json.dumps(baseline_data, indent=2) + "\n", encoding="utf-8")
    sidecar = hash_path or path.with_suffix(".sha256")
    sidecar.write_text(f"{baseline_digest(path)}  {path.name}\n", encoding="ascii")


async def evaluate(dataset_source: Optional[Union[str, Path]] = None) -> dict:
    """Run extraction and OCR evaluation across the provided dataset."""
    source_path = Path(dataset_source) if dataset_source else FIXTURES_PATH
    documents = load_dataset(source_path)

    provider = LocalExtractionProvider()
    type_counts = {entity_type: Counter() for entity_type in ENTITY_TYPES}
    category_counts = defaultdict(Counter)

    assertion_total = 0
    assertion_correct = 0

    cer_scores = []
    wer_scores = []
    bbox_iou_scores = []
    missed_terms = Counter()

    for doc in documents:
        # OCR Quality Evaluation if ocr_text is present
        if doc.ocr_text is not None:
            doc_cer = cer(doc.ground_truth_text, doc.ocr_text)
            doc_wer = wer(doc.ground_truth_text, doc.ocr_text)
            cer_scores.append(doc_cer)
            wer_scores.append(doc_wer)

        # Run Clinical Information Extraction
        output = await provider.extract_clinical_entities(doc.ground_truth_text)
        predicted_entities = output.get("entities", [])

        expected_by_key = defaultdict(list)
        actual_by_key = defaultdict(list)

        category = doc.category or "unspecified"

        for entity in doc.entities:
            expected_by_key[(entity.type, entity.normalized_value)].append(entity)
        for entity in predicted_entities:
            actual_by_key[(entity["type"], entity["normalized_value"])].append(entity)

        # Match gold vs predicted entities
        all_keys = set(expected_by_key) | set(actual_by_key)
        for key in all_keys:
            ent_type = key[0]
            exp_list = expected_by_key[key]
            act_list = actual_by_key[key]

            matched = min(len(exp_list), len(act_list))
            fp = len(act_list) - matched
            fn = len(exp_list) - matched
            if fn:
                missed_terms[(key[0], key[1])] += fn

            if ent_type in type_counts:
                type_counts[ent_type]["tp"] += matched
                type_counts[ent_type]["fp"] += fp
                type_counts[ent_type]["fn"] += fn

            category_counts[category]["tp"] += matched
            category_counts[category]["fp"] += fp
            category_counts[category]["fn"] += fn

            # Assertion matching & Bbox IoU for matched entities
            for gold_entity, pred_dict in zip(exp_list, act_list):
                assertion_total += 1
                pred_assertion = pred_dict.get("assertion", "present")
                if gold_entity.assertion == pred_assertion:
                    assertion_correct += 1

                # If bounding box is annotated in gold entity
                if gold_entity.bounding_box:
                    pred_bbox = pred_dict.get("bounding_box") or (pred_dict.get("details", {}) or {}).get("bounding_box")
                    if pred_bbox and len(pred_bbox) == 4:
                        iou = bbox_iou(gold_entity.bounding_box, pred_bbox)
                        bbox_iou_scores.append(iou)

    prec_by_type, rec_by_type, f1_by_type = _compute_prf(type_counts)
    prec_by_cat, rec_by_cat, f1_by_cat = _compute_prf(category_counts)

    mean_cer = round(sum(cer_scores) / len(cer_scores), 4) if cer_scores else None
    mean_wer = round(sum(wer_scores) / len(wer_scores), 4) if wer_scores else None
    mean_iou = round(sum(bbox_iou_scores) / len(bbox_iou_scores), 4) if bbox_iou_scores else None
    is_sample_data = source_path.name in {"fixtures.json", "annotated_samples.json"}
    noise_examples = [doc.id for doc in documents if doc.ocr_text is not None and doc.ocr_text != doc.ground_truth_text]

    return {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "fixtures_evaluated": len(documents),
        "labelled_eval_set": not is_sample_data,
        "precision_by_type": prec_by_type,
        "recall_by_type": rec_by_type,
        "f1_by_type": f1_by_type,
        "precision_by_category": prec_by_cat,
        "recall_by_category": rec_by_cat,
        "f1_by_category": f1_by_cat,
        "assertion_accuracy": round(assertion_correct / assertion_total, 4) if assertion_total else 0.0,
        "assertion_entities_evaluated": assertion_total,
        "mean_cer": mean_cer,
        "mean_wer": mean_wer,
        "ocr_documents_evaluated": len(cer_scores),
        "mean_bbox_iou": mean_iou,
        "top_missed_terms": [
            {"entity_type": entity_type, "term": term, "count": count}
            for (entity_type, term), count in missed_terms.most_common(20)
        ],
        "data_provenance": (
            "synthetic regression/sample data; OCR text differences are synthetic"
            if is_sample_data else "annotated dataset supplied to evaluator; provenance not independently verified"
        ),
        "synthetic_ocr_noise_document_ids": noise_examples if is_sample_data else [],
        "synthetic_ocr_noise_description": (
            "SAMPLE-REF-002 contains a manually changed 'pneumonia' to 'pneumonla' OCR token; this noise is synthetic."
            if source_path.name == "annotated_samples.json" else None
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run MDIS Clinical Extraction & OCR Evaluation")
    parser.add_argument("--dataset", type=str, default=None, help="Path to evaluation JSON file or corpus folder")
    parser.add_argument("--output", type=str, default=None, help="Path to write evaluation report")
    parser.add_argument("--check-baseline", action="store_true", help="Assert metrics meet baseline without drop")
    parser.add_argument("--update-baseline", action="store_true", help="Generate and update baseline.json from run")
    args = parser.parse_args()

    if not args.update_baseline and BASELINE_PATH.exists():
        try:
            verify_baseline_integrity()
        except (OSError, ValueError, IndexError) as exc:
            parser.error(str(exc))

    report = asyncio.run(evaluate(dataset_source=args.dataset))

    output_path = Path(args.output) if args.output else LATEST_PATH
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Report written to: {output_path}")

    if args.update_baseline:
        write_baseline(report, BASELINE_PATH)
        print(f"Baseline updated dynamically at: {BASELINE_PATH}")
    elif args.check_baseline:
        if not BASELINE_PATH.exists():
            print(f"Error: Baseline file does not exist at {BASELINE_PATH}")
            return 1
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        baseline_f1 = baseline.get("f1_by_type", {})
        drops = {
            name: (baseline_f1[name], value)
            for name, value in report["f1_by_type"].items()
            if name in baseline_f1 and value < baseline_f1[name]
        }
        if drops:
            print(json.dumps({"baseline_f1_drops": drops}, indent=2))
            return 1

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
