"""OCR and Layout Evaluation Metrics.

Computes Character Error Rate (CER), Word Error Rate (WER), Levenshtein edit distance,
and Bounding Box Intersection over Union (IoU).
"""

from typing import Any, Sequence


def levenshtein_distance(seq1: Sequence[Any], seq2: Sequence[Any]) -> int:
    """Compute standard Levenshtein edit distance (insertions, deletions, substitutions).

    Uses dynamic programming with O(min(m, n)) space complexity.
    """
    m, n = len(seq1), len(seq2)
    if m == 0:
        return n
    if n == 0:
        return m

    # Optimize memory to O(min(m, n))
    if m < n:
        seq1, seq2 = seq2, seq1
        m, n = n, m

    current_row = list(range(n + 1))
    for i in range(1, m + 1):
        prev_diag = current_row[0]
        current_row[0] = i
        elem1 = seq1[i - 1]
        for j in range(1, n + 1):
            temp = current_row[j]
            if elem1 == seq2[j - 1]:
                current_row[j] = prev_diag
            else:
                # 1 + min(substitution, insertion, deletion)
                current_row[j] = 1 + min(prev_diag, current_row[j - 1], current_row[j])
            prev_diag = temp

    return current_row[n]


def cer(reference: str, hypothesis: str) -> float:
    """Compute Character Error Rate (CER).

    CER = LevenshteinDistance(reference, hypothesis) / len(reference)
    """
    if not reference and not hypothesis:
        return 0.0
    if not reference:
        return 1.0
    if not hypothesis:
        return 1.0

    distance = levenshtein_distance(reference, hypothesis)
    return distance / len(reference)


def wer(reference: str, hypothesis: str) -> float:
    """Compute Word Error Rate (WER).

    WER = LevenshteinDistance(ref_tokens, hyp_tokens) / len(ref_tokens)
    """
    ref_words = reference.split()
    hyp_words = hypothesis.split()

    if not ref_words and not hyp_words:
        return 0.0
    if not ref_words:
        return 1.0
    if not hyp_words:
        return 1.0

    distance = levenshtein_distance(ref_words, hyp_words)
    return distance / len(ref_words)


def bbox_iou(box1: Sequence[float], box2: Sequence[float]) -> float:
    """Compute Intersection over Union (IoU) of two 2D bounding boxes.

    Boxes are represented as [x_min, y_min, x_max, y_max].
    Coordinates can be absolute pixel numbers or normalized [0.0, 1.0] floats.
    """
    if len(box1) != 4 or len(box2) != 4:
        raise ValueError("Bounding boxes must each have 4 elements: [x_min, y_min, x_max, y_max]")

    x1_min, y1_min, x1_max, y1_max = box1
    x2_min, y2_min, x2_max, y2_max = box2

    # Validate coordinate ordering
    if x1_max <= x1_min or y1_max <= y1_min or x2_max <= x2_min or y2_max <= y2_min:
        return 0.0

    # Intersection coordinates
    inter_x_min = max(x1_min, x2_min)
    inter_y_min = max(y1_min, y2_min)
    inter_x_max = min(x1_max, x2_max)
    inter_y_max = min(y1_max, y2_max)

    inter_width = max(0.0, inter_x_max - inter_x_min)
    inter_height = max(0.0, inter_y_max - inter_y_min)
    inter_area = inter_width * inter_height

    if inter_area <= 0.0:
        return 0.0

    area1 = (x1_max - x1_min) * (y1_max - y1_min)
    area2 = (x2_max - x2_min) * (y2_max - y2_min)
    union_area = area1 + area2 - inter_area

    if union_area <= 0.0:
        return 0.0

    return inter_area / union_area

