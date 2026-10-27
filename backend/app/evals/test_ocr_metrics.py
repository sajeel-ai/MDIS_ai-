"""Regression tests for the OCR evaluation metrics."""

import pytest

from app.evals.ocr_metrics import bbox_iou, cer, levenshtein_distance, wer


def test_cer_wer_and_levenshtein_known_values():
    assert levenshtein_distance("kitten", "sitting") == 3
    assert cer("kitten", "sitting") == pytest.approx(0.5)
    assert wer("kitten", "sitting") == pytest.approx(1.0)


def test_bbox_iou_partial_overlap():
    assert bbox_iou([0, 0, 10, 10], [5, 5, 15, 15]) == pytest.approx(1 / 7)


def test_bbox_iou_touching_boxes_have_zero_overlap():
    assert bbox_iou([0, 0, 10, 10], [10, 0, 20, 10]) == 0.0
