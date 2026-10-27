#!/usr/bin/env python
"""Compare Azure Document Intelligence OCR vs local Tesseract OCR.

Usage:
    python compare_ocr_providers.py --input-dir PATH/TO/DOCS [--ground-truth PATH/TO/gt.json]

Set env vars AZURE_DOC_INTEL_ENDPOINT and AZURE_DOC_INTEL_KEY for Azure support.
If not set, only local OCR runs.

Output: side-by-side table of CER and WER per document.

Ground-truth JSON format:
    [{"filename": "scan.pdf", "ocr_text": "expected text..."}, ...]
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.providers.ocr.local import LocalOCRProvider
from app.evals.ocr_metrics import cer, wer


async def run_local(path: Path) -> str:
    provider = LocalOCRProvider()
    result = await provider.extract_text(path.read_bytes(), mime_type=None)
    return result.text


async def run_azure(path: Path) -> str | None:
    endpoint = os.environ.get("AZURE_DOC_INTEL_ENDPOINT", "")
    key = os.environ.get("AZURE_DOC_INTEL_KEY", "")
    if not endpoint or not key:
        return None
    try:
        from app.providers.ocr.azure import AzureOCRProvider  # type: ignore[import]

        provider = AzureOCRProvider()
        result = await provider.extract_text(path.read_bytes(), mime_type=None)
        return result.text
    except Exception as e:
        print(f"  Azure error: {e}")
        return None


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, help="Directory of documents to process")
    parser.add_argument(
        "--ground-truth",
        default=None,
        help="JSON file mapping filename to ground-truth text",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.is_dir():
        print(f"ERROR: {input_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    gt_map: dict[str, str] = {}
    if args.ground_truth:
        gt_data = json.loads(Path(args.ground_truth).read_text(encoding="utf-8"))
        gt_map = {item["filename"]: item["ocr_text"] for item in gt_data}

    supported_suffixes = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif"}
    files = sorted(
        f for f in input_dir.iterdir()
        if f.is_file() and f.suffix.lower() in supported_suffixes
    )
    if not files:
        print("No supported files found.")
        return

    col_w = 40
    header = (
        f"{'File':<{col_w}} {'Local CER':>10} {'Local WER':>10} "
        f"{'Azure CER':>10} {'Azure WER':>10}"
    )
    print(header)
    print("-" * len(header))

    for f in files:
        print(f"  Processing {f.name} ...", end="\r", flush=True)
        try:
            local_text = await run_local(f)
        except Exception as exc:
            local_text = f"[ERROR: {exc}]"

        azure_text = await run_azure(f)
        gt = gt_map.get(f.name)

        if gt:
            l_cer = f"{cer(gt, local_text):.4f}"
            l_wer = f"{wer(gt, local_text):.4f}"
            a_cer = f"{cer(gt, azure_text):.4f}" if azure_text else "N/A (no creds)"
            a_wer = f"{wer(gt, azure_text):.4f}" if azure_text else "N/A (no creds)"
        else:
            l_cer = l_wer = "N/A (no GT)"
            a_cer = a_wer = "N/A (no GT)" if azure_text else "N/A (no creds)"

        name_col = f.name[:col_w]
        print(
            f"{name_col:<{col_w}} {l_cer:>10} {l_wer:>10} {a_cer:>10} {a_wer:>10}"
        )


if __name__ == "__main__":
    asyncio.run(main())

