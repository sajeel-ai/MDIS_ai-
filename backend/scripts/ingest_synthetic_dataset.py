"""Synthetic Dataset Ingestion Script.

Uploads and processes the 10 generated synthetic clinical documents into PostgreSQL
via Cognate AI REST API endpoints.
"""

import os
import sys
import time
import requests
from pathlib import Path

BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8001/api/v1")
DATASET_DIR = Path(__file__).resolve().parent.parent.parent / "storage" / "synthetic-documents"


def ingest_dataset():
    print(f"Connecting to Cognate AI backend at {BASE_URL}...")
    try:
        res = requests.get(f"{BASE_URL}/health")
        if res.status_code != 200:
            print(f"Error: API health check returned status {res.status_code}")
            sys.exit(1)
        print("✓ Cognate AI backend connection successful.")
    except Exception as exc:
        print(f"Error connecting to backend: {exc}")
        print("Ensure FastAPI dev server is running on port 8001 (npm run dev).")
        sys.exit(1)

    # 1. Fetch active patients
    pat_res = requests.get(f"{BASE_URL}/patients?page=1&page_size=20")
    patients = pat_res.json().get("items", [])
    if not patients:
        print("Error: No patients found in PostgreSQL database.")
        sys.exit(1)

    print(f"✓ Found {len(patients)} patients in database.")

    txt_files = sorted(list(DATASET_DIR.glob("*.txt")))
    if not txt_files:
        print("No .txt documents found. Run generate_synthetic_dataset.py first.")
        sys.exit(1)

    print(f"\nIngesting {len(txt_files)} synthetic clinical documents...\n")

    for i, file_path in enumerate(txt_files):
        patient = patients[i % len(patients)]
        doc_type_name = file_path.stem.replace("doc_", "").split("_")[1]

        with open(file_path, "rb") as f:
            file_bytes = f.read()

        print(f"[{i+1}/{len(txt_files)}] Uploading {file_path.name} ({len(file_bytes)} bytes)...")
        up_res = requests.post(
            f"{BASE_URL}/documents/upload",
            data={
                "patient_id": patient["id"],
                "document_type": doc_type_name,
            },
            files={
                "file": (file_path.name, file_bytes, "text/plain"),
            },
        )

        if up_res.status_code not in [200, 201]:
            print(f"  ✗ Upload failed ({up_res.status_code}): {up_res.text}")
            continue

        doc_data = up_res.json()
        doc_id = doc_data["id"]
        print(f"  ✓ Uploaded Document ID: {doc_id}")

        # Trigger workflow execution
        proc_res = requests.post(f"{BASE_URL}/documents/{doc_id}/process")
        if proc_res.status_code != 200:
            print(f"  ✗ Processing initiation failed ({proc_res.status_code}): {proc_res.text}")
            continue

        job_id = proc_res.json()["job_id"]
        print(f"  ⚡ Processing Job: {job_id}")

        # Poll status for up to 5 seconds
        for _ in range(5):
            time.sleep(1)
            j_status_res = requests.get(f"{BASE_URL}/processing/{job_id}")
            j_data = j_status_res.json()
            status = j_data.get("status")
            if status in ["completed", "failed"]:
                print(f"  → Result Status: {status.upper()}")
                if status == "failed":
                    print(f"    Error: {j_data.get('error_message')}")
                break

        print()

    print("Synthetic dataset ingestion cycle completed.")


if __name__ == "__main__":
    ingest_dataset()
