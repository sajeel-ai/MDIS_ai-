# Cognate AI — API Contract

**Status: LOCKED — Phase 2 implementation baseline**  
**Backend: FastAPI**  
**Base URL: `http://localhost:8001`**  
**API Prefix: `/api/v1`**  
**Content-Type: `application/json`**

---

## Derivation Methodology

This contract was derived directly from the existing React frontend's data consumption:

| Source | What was inspected |
|---|---|
| `src/data/mockData.ts` | All exported mock objects (CASES, EXTRACTIONS, REVIEW_QUEUE, TIMELINE_EVENTS, PIPELINE_STAGES, CLINICAL_NOTE) |
| `src/types/*.ts` | DocumentItem, ClinicalEntity, ReviewItem, WorkflowItem, AIEvaluationMetric, SystemTelemetry |
| `src/pages/*.tsx` | Every field accessed in JSX for each page |
| `src/views/*.tsx` | ClinicalWorkspace (3-panel), ReviewCenter, Dashboard, AIOperations |

The API response shapes below **exactly match** what the current UI renders.
No JSX changes are required after this migration.

---

## Common Patterns

### Pagination Envelope

All list endpoints return:

```json
{
  "items": [...],
  "total": 348,
  "page": 1,
  "page_size": 25,
  "has_next": true
}
```

### Error Response

```json
{
  "error": "not_found",
  "message": "Document with id 'abc-123' does not exist",
  "status_code": 404
}
```

### Status Enums

```typescript
// Document processing status (maps to document_versions pipeline)
DocumentStatus = 'queued' | 'ocr_processing' | 'extracting' | 'validating' | 'completed' | 'failed'

// Review task status
ReviewStatus = 'pending' | 'in_review' | 'approved' | 'rejected' | 'needs_correction'

// Review priority
ReviewPriority = 'high' | 'medium' | 'normal'
```

---

## Endpoints

---

### `GET /api/v1/dashboard`

**Consumer:** `src/views/Dashboard.tsx` (KPI row, Review Queue, Recent Cases table)

**Query params:** none

**Response:**

```json
{
  "metrics": {
    "total_documents":   12480,
    "processed":         11932,
    "pending_review":    348,
    "failed":            200,
    "success_rate":      0.956,
    "last_updated_at":   "2026-09-22T09:14:00Z"
  },
  "review_queue_summary": {
    "high_priority":     12,
    "medium_priority":   48,
    "standard":          288,
    "ai_conflicts":      17
  },
  "extraction_quality": [
    { "entity_type": "diagnoses",    "accuracy": 0.96 },
    { "entity_type": "medications",  "accuracy": 0.94 },
    { "entity_type": "symptoms",     "accuracy": 0.91 },
    { "entity_type": "procedures",   "accuracy": 0.89 },
    { "entity_type": "temporal",     "accuracy": 0.87 }
  ],
  "recent_cases": [
    {
      "id":            "CL-102938",
      "patient_name":  "Margaret T.",
      "mrn":           "MRN-448821",
      "doc_type":      "Discharge Summary",
      "status":        "completed",
      "confidence":    "high",
      "review_status": "Pending Review",
      "last_updated":  "2026-09-22T09:14:00Z",
      "entity_counts": { "diagnoses": 4, "medications": 6, "symptoms": 5, "procedures": 2 }
    }
  ]
}
```

**Notes:**
- All numeric metrics are computed from the database at query time — no hardcoded values.
- `recent_cases` returns the 10 most recently updated documents with extracted data.

---

### `GET /api/v1/documents`

**Consumer:** `src/pages/Documents.tsx` (document table)

**Query params:**

| Param | Type | Default | Description |
|---|---|---|---|
| `page` | int | 1 | Page number |
| `page_size` | int | 25 | Items per page |
| `status` | string | — | Filter by processing status |
| `search` | string | — | Filter by patient name, MRN, doc type, or case ID |

**Response:**

```json
{
  "items": [
    {
      "id":           "doc-abc-123",
      "case_id":      "CL-102938",
      "patient_name": "Margaret T.",
      "mrn":          "MRN-448821",
      "doc_type":     "Discharge Summary",
      "status":       "completed",
      "confidence":   "high",
      "last_updated": "2026-09-22T09:14:00Z"
    }
  ],
  "total": 12480,
  "page": 1,
  "page_size": 25,
  "has_next": true
}
```

**Notes:**
- `confidence` is derived from the most recent extraction's average entity confidence:
  `>= 0.85 → "high"`, `>= 0.65 → "medium"`, `< 0.65 → "low"`.
- `case_id` is a human-readable identifier (e.g., `CL-102938`) generated from the document UUID.

---

### `GET /api/v1/documents/{id}`

**Consumer:** `src/views/ClinicalWorkspace.tsx` (left panel — document viewer)

**Response:**

```json
{
  "id":           "doc-abc-123",
  "case_id":      "CL-102938",
  "patient_name": "Margaret T.",
  "mrn":          "MRN-448821",
  "dob":          "1958-03-14",
  "doc_type":     "Discharge Summary",
  "status":       "completed",
  "source_text":  "DISCHARGE SUMMARY\n\nPatient: Margaret T.\n...",
  "version_number": 1,
  "page_count":   3,
  "file_name":    "discharge_summary_margaret_t.pdf",
  "mime_type":    "application/pdf",
  "size_bytes":   42318,
  "last_updated": "2026-09-22T09:14:00Z",
  "pipeline_stages": [
    { "name": "Uploaded",             "status": "done",    "detail": "2026-09-22 07:00", "throughput": "—" },
    { "name": "Validated",            "status": "done",    "detail": "Schema OK",          "throughput": "—" },
    { "name": "Preprocessed",         "status": "done",    "detail": "Text extracted, 4.2 KB", "throughput": "—" },
    { "name": "NLP Analysis",         "status": "done",    "detail": "38 entities detected", "throughput": "1.2s" },
    { "name": "LLM Extraction",       "status": "done",    "detail": "claude-sonnet-5",    "throughput": "4.8s" },
    { "name": "Schema Validation",    "status": "done",    "detail": "All fields present", "throughput": "—" },
    { "name": "Medical Normalization","status": "done",    "detail": "SNOMED/ICD mapped",  "throughput": "0.8s" },
    { "name": "Final Review",         "status": "active",  "detail": "Awaiting clinician", "throughput": "—" },
    { "name": "Completed",            "status": "pending", "detail": "—",                  "throughput": "—" }
  ]
}
```

**Notes:**
- `source_text` comes from `document_versions.raw_text` (latest version).
- `pipeline_stages` is constructed from `processing_steps` joined to the latest `processing_job`.

---

### `GET /api/v1/documents/{id}/entities`

**Consumer:** `src/views/ClinicalWorkspace.tsx` (right panel — entity cards)

**Response:**

```json
{
  "extraction_id": "extract-xyz",
  "model_name":    "claude-sonnet-5",
  "model_version": "2026-09",
  "diagnoses": [
    {
      "id":               "entity-d1",
      "name":             "Chronic Obstructive Pulmonary Disease",
      "abbreviation":     "COPD",
      "status":           "Active",
      "confidence":       "high",
      "confidence_score": 0.9640,
      "standard":         "SNOMED CT",
      "code":             "13645005",
      "evidence":         "Patient is a 68-year-old female with a history of COPD...",
      "source_ref":       "HISTORY OF PRESENT ILLNESS",
      "review_status":    "Pending",
      "review_reason":    null
    }
  ],
  "medications": [
    {
      "id":               "entity-m1",
      "name":             "Lisinopril",
      "dose":             "10 mg",
      "frequency":        "Once daily",
      "route":            "Oral",
      "status":           "Active",
      "confidence":       "high",
      "confidence_score": 0.9820,
      "interaction_flag":    false,
      "interaction_detail":  null
    }
  ],
  "symptoms": [
    {
      "id":           "entity-s1",
      "name":         "Dyspnea",
      "severity":     "Moderate",
      "onset":        "3 days prior",
      "confidence":   "high",
      "confidence_score": 0.9410
    }
  ],
  "ai_details": {
    "model":           "claude-sonnet-5",
    "pipeline":        "v1.4.2",
    "timestamp":       "2026-09-22T09:14:00Z",
    "schema_valid":    true,
    "terminology":     "normalized"
  }
}
```

---

### `GET /api/v1/documents/{id}/evidence`

**Consumer:** `src/views/ClinicalWorkspace.tsx` — "View Source" button highlights evidence span

**Query params:**

| Param | Type | Description |
|---|---|---|
| `entity_id` | string | The entity whose span(s) to return |

**Response:**

```json
{
  "entity_id":    "entity-d4",
  "entity_name":  "Community-Acquired Pneumonia",
  "spans": [
    {
      "span_id":      "span-001",
      "page_number":  1,
      "start_offset": 482,
      "end_offset":   512,
      "text":         "possible community-acquired pneumonia"
    }
  ]
}
```

---

### `GET /api/v1/cases`

**Consumer:** `src/views/Dashboard.tsx` → Recent Cases table; `src/pages/Documents.tsx`

Same response shape as `GET /api/v1/documents` — `cases` is a semantic alias
that always returns documents that have at least one extraction attached.

---

### `GET /api/v1/patients/{id}`

**Consumer:** `src/views/PatientTimeline.tsx`

**Response:**

```json
{
  "id":           "patient-abc",
  "mrn":          "MRN-448821",
  "first_name":   "Margaret",
  "last_name":    "T.",
  "dob":          "1958-03-14",
  "gender":       "F",
  "encounters": [
    {
      "id":          "encounter-001",
      "admit_time":  "2026-09-15T08:00:00Z",
      "discharge_time": "2026-09-22T14:00:00Z",
      "los_hours":   150,
      "icd_codes": [
        { "code": "J44.1", "description": "COPD exacerbation", "is_primary": true }
      ]
    }
  ]
}
```

---

### `GET /api/v1/patients/{id}/timeline`

**Consumer:** `src/views/PatientTimeline.tsx` (timeline events list)

**Response:**

```json
{
  "patient_id": "patient-abc",
  "events": [
    {
      "date":   "2026-09-15",
      "type":   "encounter",
      "title":  "Hospital Admission",
      "detail": "Admitted for acute COPD exacerbation"
    },
    {
      "date":   "2026-09-15",
      "type":   "diagnosis",
      "title":  "COPD Exacerbation Confirmed",
      "detail": "Acute exacerbation, SNOMED CT 13645005"
    },
    {
      "date":   "2026-09-15",
      "type":   "medication",
      "title":  "Corticosteroids initiated",
      "detail": "Prednisone 40mg once daily"
    }
  ]
}
```

**`type` values:** `encounter | diagnosis | medication | procedure | lab | note`

---

### `GET /api/v1/review/queue`

**Consumer:** `src/views/ReviewCenter.tsx` (queue list + review panel)

**Query params:**

| Param | Type | Default | Description |
|---|---|---|---|
| `priority` | string | — | Filter: `high`, `medium`, `normal` |
| `status` | string | `pending` | Filter by review status |
| `page` | int | 1 | Pagination |
| `page_size` | int | 25 | Items per page |

**Response:**

```json
{
  "items": [
    {
      "id":           "rv1",
      "priority":     "high",
      "case_id":      "CL-102944",
      "patient":      "Aisha K.",
      "entity_type":  "Diagnosis",
      "entity":       "Community-Acquired Pneumonia",
      "reason":       "Ambiguous evidence",
      "confidence":   "low",
      "source_text":  "...possible community-acquired pneumonia, right lower lobe...",
      "ai_extraction":"Community-Acquired Pneumonia — Possible, Right Lower Lobe",
      "review_reason":"Evidence was ambiguous — \"possible\" qualifier detected."
    }
  ],
  "total": 348,
  "page": 1,
  "page_size": 25,
  "has_next": true
}
```

---

### `GET /api/v1/review/{id}`

**Consumer:** `src/views/ReviewCenter.tsx` — single review panel open state

Returns the same shape as a single item from `GET /api/v1/review/queue`.

---

### `POST /api/v1/review/{id}/decision`

**Consumer:** `src/views/ReviewCenter.tsx` — Accept / Reject / Skip buttons

**Request body:**

```json
{
  "decision": "approved",
  "comment":  "Confirmed diagnosis based on clinical context",
  "edited_value": null
}
```

| Field | Values |
|---|---|
| `decision` | `"approved"` \| `"rejected"` \| `"needs_correction"` |
| `comment` | Optional free-text comment |
| `edited_value` | Optional corrected extraction value (used when decision is `"needs_correction"`) |

**Response:** `204 No Content` on success.

---

### `GET /api/v1/aiops/metrics`

**Consumer:** `src/views/AIOperations.tsx` (KPI tiles, extraction quality bars, model config)

**Response:**

```json
{
  "kpis": {
    "documents_processed": 125430,
    "success_rate":         0.982,
    "review_rate":          0.074,
    "failure_rate":         0.018
  },
  "extraction_quality": [
    { "label": "Diagnoses",     "accuracy": 0.96, "entity_type": "diagnosis" },
    { "label": "Medications",   "accuracy": 0.94, "entity_type": "medication" },
    { "label": "Symptoms",      "accuracy": 0.91, "entity_type": "symptom" },
    { "label": "Procedures",    "accuracy": 0.89, "entity_type": "procedure" },
    { "label": "Lab Values",    "accuracy": 0.88, "entity_type": "lab_result" },
    { "label": "Temporal Data", "accuracy": 0.87, "entity_type": "temporal" }
  ],
  "model_config": {
    "active_model":     "claude-sonnet-5",
    "model_version":    "2026-09",
    "pipeline_version": "v1.4.2",
    "prompt_version":   "clinical-v3.1",
    "avg_latency_s":    4.8,
    "avg_tokens_in":    3240,
    "avg_tokens_out":   1820,
    "cost_per_doc":     0.024,
    "retry_rate":       0.021
  },
  "measurement_period": "Last 30 days",
  "dataset_context":    "Production — all document types"
}
```

---

### `GET /api/v1/aiops/jobs`

**Consumer:** `src/views/AIOperations.tsx` (Data Pipeline Health nodes)

**Response:**

```json
{
  "pipeline_nodes": [
    { "name": "EHR/EMR",       "status": "healthy", "throughput": "1,240/hr", "latency": "—",    "note": null },
    { "name": "Ingestion",     "status": "healthy", "throughput": "1,238/hr", "latency": "0.3s", "note": null },
    { "name": "Clinical NLP",  "status": "warn",    "throughput": "1,225/hr", "latency": "1.4s", "note": "3 failures" },
    { "name": "LLM Extraction","status": "healthy", "throughput": "1,222/hr", "latency": "4.8s", "note": null }
  ]
}
```

---

### `GET /api/v1/aiops/health`

**Consumer:** `src/components/navigation/Header.tsx` (system status indicator)

**Response:**

```json
{
  "status": "nominal",
  "message": "All systems nominal"
}
```

`status` values: `"nominal"` | `"degraded"` | `"outage"`

---

## Deferred Endpoints (Phase D9+)

These endpoints are defined in the contract now but are **not implemented in Phase 2**:

```
POST /api/v1/documents/upload        → Document ingestion trigger
POST /api/v1/documents/{id}/process  → Manually trigger re-processing
POST /api/v1/workflows/{id}/run      → Execute a defined workflow
GET  /api/v1/workflows               → Workflow list
GET  /api/v1/workflows/{id}          → Workflow detail with nodes and edges
```

---

## Frontend Service Layer Mapping

| Page / View | Current data source | Target service | Target endpoint |
|---|---|---|---|
| `Dashboard.tsx` | `CASES` from mockData | `dashboardService.getMetrics()` | `GET /api/v1/dashboard` |
| `Documents.tsx` | `CASES` from mockData | `documentService.getDocuments()` | `GET /api/v1/documents` |
| `ClinicalWorkspace.tsx` | `CLINICAL_NOTE`, `EXTRACTIONS`, `PIPELINE_STAGES` | `documentService.getDocument()` + `getEntities()` | `GET /api/v1/documents/{id}` + `/entities` |
| `ReviewCenter.tsx` | `REVIEW_QUEUE` from mockData | `reviewService.getQueue()` | `GET /api/v1/review/queue` |
| `PatientTimeline.tsx` | `TIMELINE_EVENTS` from mockData | `patientService.getTimeline()` | `GET /api/v1/patients/{id}/timeline` |
| `AIOperations.tsx` | Inline constants | `aiOpsService.getMetrics()` | `GET /api/v1/aiops/metrics` |
| `Header.tsx` | Hardcoded "All systems nominal" | `aiOpsService.getHealth()` | `GET /api/v1/aiops/health` |

---

## Environment Configuration

**Frontend** (`.env.local`):

```
VITE_API_URL=http://localhost:8001
```

**Backend** (`.env`):

```
DATABASE_URL=postgresql+asyncpg://cognate:cognate@localhost:5432/cognate
STORAGE_BACKEND=local
STORAGE_LOCAL_PATH=./storage
CORS_ORIGINS=http://localhost:8443,http://localhost:5173
```

**`src/services/apiClient.ts` — real implementation:**

```typescript
const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8001';

export async function apiClient<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${endpoint}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.message ?? `HTTP ${response.status}`);
  }

  return response.json() as Promise<T>;
}
```
