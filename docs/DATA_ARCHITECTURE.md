# Cognate AI — Data Architecture

**Status: LOCKED — Phase 2 implementation baseline**  
**Date: 2026-09-22**

---

## 1. Guiding Principle

Every data design decision in Cognate AI is driven by one requirement:

> An extracted clinical entity must be fully traceable from its normalized value
> back through the model that produced it, the processing job that ran it,
> the version of the document text it was extracted from, and the exact character
> span in the original source.

This is called **full extraction provenance** and it is the foundation of the
Evidence panel in the Clinical Workspace.

---

## 2. System Overview

```
COGNATE AI — DATA FLOW

Documents ──► Processing Jobs ──► Extractions ──► Clinical Entities ──► Evidence Spans
                   │                                      │
                   ▼                                      ▼
            Processing Steps                    Validation Results
                                                       │
                                                       ▼
                                                 Review Tasks ──► Audit Events
```

---

## 3. Dataset Strategy

Three datasets are used at different phases. They are never mixed.

### Dataset A — Synthetic (Development)

**Purpose:** Frontend development, API integration, UI demos, CI/CD.

- Hand-crafted documents with known ground-truth extractions.
- No real patient information.
- Stored in `data/sample/`.
- Used by default in local development when MIMIC is not loaded.

**Scope:** ~20 documents, ~5 patients, covering all entity types and edge cases
(ambiguous diagnoses, interaction flags, low-confidence items).

### Dataset B — MIMIC-IV Demo (Relational Testing)

**Purpose:** Realistic relational structure — patients, encounters, ICD codes,
demographics, admission metadata.

- Openly available at PhysioNet (100 patients, ~200 admissions).
- Provides realistic `patients`, `encounters`, and `icd_codes` structure.
- Does **not** provide rich free-text clinical notes for NLP work.
- MIMIC-IV patient IDs are stored as `external_patient_id`, not as MRNs.

**Scope:** 100 patients, ~200 encounters, ICD-9/ICD-10 diagnoses.

### Dataset C — MIMIC-IV-Note (NLP Evaluation)

**Purpose:** Realistic free-text clinical document extraction and evaluation.

- Requires PhysioNet credentialing and a signed Data Use Agreement.
- Contains 331,794 deidentified discharge summaries and 2,321,355 deidentified
  radiology reports.
- Used for extraction model evaluation only — not for frontend development.
- Not loaded into the development database.

**Scope:** Evaluated offline via batch pipeline scripts.

---

## 4. Storage Architecture

### Relational Data — PostgreSQL 16

All structured application data lives in PostgreSQL.

```
patients, encounters, documents, document_versions
processing_jobs, processing_steps
extractions, clinical_entities, evidence_spans
validation_results, review_tasks
users, audit_events, icd_codes
```

**Extension:** `pgvector` is installed but not used in Phase 2.
It is reserved for future semantic search.

### Document Files — Local Object Storage (Phase 2)

In Phase 2, uploaded document files (PDF, image) are written to:

```
storage/documents/{document_id}/{filename}
```

The `documents.storage_key` column holds the relative path.

Later phases will replace this with S3-compatible object storage (MinIO or AWS S3).
The `storage_key` format is designed to be path-agnostic:

```
local:documents/abc-123/discharge_summary.pdf
s3:cognate-documents/abc-123/discharge_summary.pdf
```

### Environment Variables

```
DATABASE_URL=postgresql+asyncpg://cognate:cognate@localhost:5432/cognate
STORAGE_BACKEND=local
STORAGE_LOCAL_PATH=./storage
VITE_API_URL=http://localhost:8001
```

---

## 5. Migration Path

```
D1  Real data contract (TypeScript types + Zod + API response shapes)
 ↓
D2  Database foundation (PostgreSQL schema + Alembic migrations)
 ↓
D3  Data ingestion (MIMIC-IV Demo + synthetic sample documents)
 ↓
D4  FastAPI backend (routers, schemas, services, DB queries)
 ↓
D5  Vertical slice (1 patient → 1 encounter → 1 document → full pipeline)
 ↓
D6  Frontend migration (mock services → real API calls, page by page)
 ↓
D7  Scale (100 MIMIC-IV patients, full development corpus)
 ↓
D8  MIMIC-IV-Note evaluation (offline NLP pipeline)
 ↓
D9  AI pipeline (OCR → Extraction → Validation, real documents)
 ↓
D10 Security + Audit (HIPAA-aligned audit logging)
 ↓
D11 Evaluation and production POC
```

---

## 6. Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Primary database | PostgreSQL 16 | Strong relational integrity for clinical relationships; MIMIC-IV is relational |
| Document text storage | `document_versions` table | Supports OCR re-runs; text changes are versioned |
| Evidence storage | `evidence_spans` (separate table) | One entity → multiple spans; character-level precision |
| MIMIC IDs | `external_patient_id` | Never conflate research IDs with real MRNs |
| Vector DB | pgvector (not active) | Future semantic search without a separate service |
| Object storage | Local path in Phase 2 → S3 later | `storage_key` is path-agnostic from day one |
| Authentication | None in Phase 2 (localhost only) | API designed for JWT middleware insertion later |
| Async processing | Synchronous in Phase 2 | Celery/RQ added in D9 when real pipeline runs |
