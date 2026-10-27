"""Unit tests for OCR evaluation metrics: CER, WER, Levenshtein distance, and BBox IoU."""

import pytest
from app.evals.ocr_metrics import (
    levenshtein_distance,
    cer,
    wer,
    bbox_iou,
)


def test_levenshtein_distance_known_cases():
    assert levenshtein_distance("", "") == 0
    assert levenshtein_distance("a", "") == 1
    assert levenshtein_distance("", "b") == 1
    assert levenshtein_distance("kitten", "sitting") == 3
    assert levenshtein_distance("saturday", "sunday") == 3
    assert levenshtein_distance(["the", "cat"], ["the", "dog"]) == 1
    assert levenshtein_distance(["a", "b", "c"], ["a", "c"]) == 1


def test_cer_known_cases():
    # Exact match
    assert cer("patient", "patient") == 0.0
    
    # Single substitution: 1 / 4 = 0.25
    assert cer("test", "tent") == 0.25
    
    # Single deletion: 1 / 4 = 0.25
    assert cer("test", "tst") == 0.25
    
    # Single insertion: 1 / 4 = 0.25
    assert cer("test", "tests") == 0.25
    
    # Boundary / empty cases
    assert cer("", "") == 0.0
    assert cer("", "nonempty") == 1.0
    assert cer("nonempty", "") == 1.0


def test_wer_known_cases():
    # Exact match
    assert wer("patient has cough", "patient has cough") == 0.0
    
    # 1 word substituted out of 4: 1 / 4 = 0.25
    assert wer("the quick brown fox", "the fast brown fox") == 0.25
    
    # 1 word inserted: 1 / 2 = 0.5
    assert wer("patient coughs", "patient now coughs") == 0.5
    
    # 1 word deleted: 1 / 3 = 0.3333...
    assert pytest.approx(wer("patient has fever", "patient fever"), rel=1e-3) == 1 / 3
    
    # Boundary / empty cases
    assert wer("", "") == 0.0
    assert wer("", "hello world") == 1.0
    assert wer("hello world", "") == 1.0


def test_bbox_iou_known_cases():
    # Identical bounding boxes: IoU = 1.0
    assert bbox_iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0
    assert bbox_iou([0.1, 0.2, 0.8, 0.9], [0.1, 0.2, 0.8, 0.9]) == 1.0
    
    # Disjoint bounding boxes: IoU = 0.0
    assert bbox_iou([0, 0, 10, 10], [20, 20, 30, 30]) == 0.0
    
    # Adjacent touching edges: IoU = 0.0
    assert bbox_iou([0, 0, 1, 1], [1, 1, 2, 2]) == 0.0
    
    # Known overlap:
    # Box A: [0, 0, 2, 2] -> Area = 4
    # Box B: [1, 1, 3, 3] -> Area = 4
    # Intersection: [1, 1, 2, 2] -> Area = 1
    # Union: 4 + 4 - 1 = 7
    # IoU = 1 / 7
    assert pytest.approx(bbox_iou([0, 0, 2, 2], [1, 1, 3, 3]), rel=1e-4) == 1 / 7
    
    # Contained box:
    # Outer: [0, 0, 4, 4] -> Area = 16
    # Inner: [1, 1, 3, 3] -> Area = 4
    # Intersection: Area = 4
    # Union: 16 + 4 - 4 = 16
    # IoU = 4 / 16 = 0.25
    assert bbox_iou([0, 0, 4, 4], [1, 1, 3, 3]) == 0.25
    
    # Degenerate zero-area box
    assert bbox_iou([0, 0, 0, 0], [1, 1, 2, 2]) == 0.0

