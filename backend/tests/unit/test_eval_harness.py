"""Regression checks for the synthetic extraction evaluation data and report."""

import asyncio
import json
import sys
from pathlib import Path

import pytest
from app.evals.run_eval import evaluate, main, verify_baseline_integrity, write_baseline
from app.evals import run_eval as eval_module


EVAL_DIR = Path(__file__).resolve().parents[2] / "evals"


def test_baseline_must_match_run_eval_generated_hash(tmp_path):
    baseline = tmp_path / "baseline.json"
    digest = tmp_path / "baseline.sha256"
    report = {
        "measured_at": "2026-10-27T00:00:00+00:00",
        "f1_by_type": {}, "f1_by_category": {}, "assertion_accuracy": 1.0,
        "mean_cer": 0.0, "mean_wer": 0.0,
    }
    write_baseline(report, baseline, digest)
    verify_baseline_integrity(baseline, digest)
    baseline.write_text(baseline.read_text(encoding="utf-8").replace('"mean_cer": 0.0', '"mean_cer": 0.5'), encoding="utf-8")
    with pytest.raises(ValueError, match="integrity check failed"):
        verify_baseline_integrity(baseline, digest)


def test_run_eval_updates_and_seals_baseline(tmp_path, monkeypatch):
    baseline = tmp_path / "baseline.json"
    latest = tmp_path / "latest.json"
    monkeypatch.setattr(eval_module, "BASELINE_PATH", baseline)
    monkeypatch.setattr(eval_module, "LATEST_PATH", latest)
    monkeypatch.setattr(sys, "argv", ["run_eval.py", "--update-baseline"])
    assert main() == 0
    verify_baseline_integrity(baseline)
    assert json.loads(baseline.read_text(encoding="utf-8"))["generated_at"]
    assert latest.exists()


def test_eval_includes_at_least_thirty_synthetic_fixtures_and_metrics():
    fixtures_path = EVAL_DIR / "fixtures.json"
    fixtures = json.loads(fixtures_path.read_text(encoding="utf-8"))
    assert len(fixtures) >= 30
    report = asyncio.run(evaluate())
    assert report["fixtures_evaluated"] == len(fixtures)
    assert set(report["f1_by_type"]) == {"diagnosis", "medication", "symptom", "procedure", "lab"}
    assert set(report["precision_by_type"]) == set(report["f1_by_type"])
    assert set(report["recall_by_type"]) == set(report["f1_by_type"])
    assert 0 <= report["assertion_accuracy"] <= 1
    assert report["labelled_eval_set"] is False
    assert "synthetic" in report["data_provenance"]


def test_eval_with_annotated_samples_computes_category_and_ocr_metrics():
    sample_path = EVAL_DIR / "annotated_samples.json"
    assert sample_path.exists()
    
    report = asyncio.run(evaluate(dataset_source=sample_path))
    assert report["fixtures_evaluated"] == 5
    
    # Per-category metrics must be present
    assert "f1_by_category" in report
    assert "precision_by_category" in report
    assert "recall_by_category" in report
    assert set(report["f1_by_category"].keys()) == {
        "discharge_summary",
        "progress_note",
        "lab_report",
        "emergency_note",
        "radiology_report",
    }
    
    # OCR metrics must be present and bounded
    assert "mean_cer" in report
    assert "mean_wer" in report
    assert 0.0 <= report["mean_cer"] <= 1.0
    assert 0.0 <= report["mean_wer"] <= 1.0
    assert report["ocr_documents_evaluated"] == 5
