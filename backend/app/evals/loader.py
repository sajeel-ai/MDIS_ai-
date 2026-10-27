"""Evaluation Dataset Loader for MDIS.

Loads annotated reference documents from single JSON files or a multi-document corpus
directory, supporting both the full annotation schema and legacy fixture formats.
"""

import json
from pathlib import Path
from typing import List, Union

from app.evals.schema import AnnotatedDocument, AnnotatedEntity, Span


def parse_document_dict(doc_data: dict, default_id: str = "DOC-UNKNOWN") -> AnnotatedDocument:
    """Parse a document dictionary into an AnnotatedDocument instance."""
    # Check if this is the modern schema
    if "ground_truth_text" in doc_data:
        entities = []
        for e in doc_data.get("entities", []):
            span = None
            if "span" in e and e["span"]:
                span = Span(**e["span"]) if isinstance(e["span"], dict) else Span(start_offset=e["span"][0], end_offset=e["span"][1])
            entities.append(
                AnnotatedEntity(
                    type=e["type"],
                    text=e.get("text"),
                    normalized_value=e["normalized_value"],
                    span=span,
                    negated=bool(e.get("negated", False)),
                    temporality=e.get("temporality", "current"),
                    assertion=e.get("assertion", "present"),
                    bounding_box=e.get("bounding_box"),
                    code=e.get("code"),
                    code_system=e.get("code_system"),
                )
            )
        return AnnotatedDocument(
            id=doc_data.get("id", default_id),
            category=doc_data.get("category", "unspecified"),
            ground_truth_text=doc_data["ground_truth_text"],
            ocr_text=doc_data.get("ocr_text"),
            entities=entities,
            metadata=doc_data.get("metadata", {}),
        )

    # Legacy fixture format: {"text": "...", "entities": [...]}
    text = doc_data.get("text", "")
    entities = []
    for e in doc_data.get("entities", []):
        entities.append(
            AnnotatedEntity(
                type=e["type"],
                text=e.get("text"),
                normalized_value=e["normalized_value"],
                assertion=e.get("assertion", "present"),
            )
        )
    return AnnotatedDocument(
        id=doc_data.get("id", default_id),
        category=doc_data.get("category", "unspecified"),
        ground_truth_text=text,
        ocr_text=doc_data.get("ocr_text"),
        entities=entities,
        metadata=doc_data.get("metadata", {}),
    )


def load_dataset(source: Union[str, Path]) -> List[AnnotatedDocument]:
    """Load evaluation documents from a JSON file or a directory containing JSON files.

    Handles single files (e.g. fixtures.json, annotated_samples.json) and corpus
    directories containing multiple document JSON files (supporting 250+ collections).
    """
    path = Path(source).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Evaluation source path does not exist: {path}")

    documents: List[AnnotatedDocument] = []

    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            for idx, item in enumerate(data):
                doc_id = item.get("id", f"{path.stem}_{idx + 1:04d}")
                documents.append(parse_document_dict(item, default_id=doc_id))
        elif isinstance(data, dict):
            documents.append(parse_document_dict(data, default_id=path.stem))
    elif path.is_dir():
        # Scan for all .json files in directory
        for json_file in sorted(path.glob("**/*.json")):
            # Skip report or baseline files if they happen to be in the same folder
            if json_file.name in {"latest_eval.json", "baseline.json", "annotation_schema.json"}:
                continue
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    for idx, item in enumerate(data):
                        doc_id = item.get("id", f"{json_file.stem}_{idx + 1:04d}")
                        documents.append(parse_document_dict(item, default_id=doc_id))
                elif isinstance(data, dict):
                    documents.append(parse_document_dict(data, default_id=json_file.stem))
            except Exception as exc:
                print(f"Warning: Failed to parse {json_file}: {exc}")

    return documents

