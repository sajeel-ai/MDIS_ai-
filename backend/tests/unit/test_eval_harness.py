"""Regression checks for the synthetic extraction evaluation data and report."""

import asyncio
import json
from pathlib import Path

from app.evals.run_eval import evaluate


def test_eval_includes_at_least_thirty_synthetic_fixtures_and_metrics():
    fixtures_path = Path(__file__).resolve().parents[2] / "evals" / "fixtures.json"
    fixtures = json.loads(fixtures_path.read_text(encoding="utf-8"))
    assert len(fixtures) >= 30
    report = asyncio.run(evaluate())
    assert report["fixtures_evaluated"] == len(fixtures)
    assert set(report["f1_by_type"]) == {"diagnosis", "medication", "symptom", "procedure", "lab"}
    assert set(report["precision_by_type"]) == set(report["f1_by_type"])
    assert set(report["recall_by_type"]) == set(report["f1_by_type"])
    assert 0 <= report["assertion_accuracy"] <= 1
