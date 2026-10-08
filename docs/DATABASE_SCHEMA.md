# Cognate AI — Database Schema

**Status: LOCKED — Phase 2 implementation baseline**  
**Database: PostgreSQL 16**  
**ORM: SQLAlchemy 2.x (async)**  
**Migrations: Alembic**

---

## Entity Relationship Overview

```
patients
   │
   └── encounters
          │
          └── documents
                 │
                 ├── document_versions
                 │
                 ├── processing_jobs
                 │      └── processing_steps
                 │
                 └── extractions
                        └── clinical_entities
                               ├── evidence_spans ──► document_versions
                               └── validation_results

clinical_entities
   └── review_tasks ──► users

users
   └── audit_events
```

---

## Tables

### `patients`

```sql
CREATE TABLE patients (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_patient_id VARCHAR(64),          -- MIMIC-IV subject_id or other source ID
    mrn                 VARCHAR(32),          -- Internal MRN (application-assigned, nullable)
    first_name          VARCHAR(128),
    last_name           VARCHAR(128),
    dob                 DATE,
    gender              VARCHAR(16),          -- 'M' | 'F' | 'Unknown'
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_patients_external_id ON patients(external_patient_id);
CREATE INDEX idx_patients_mrn ON patients(mrn);
```

**Notes:**
- `external_patient_id` holds the MIMIC-IV `subject_id` or other source system ID.
- `mrn` is an optional internal identifier — never conflate with the MIMIC subject_id.
- For synthetic Dataset A, `external_patient_id` is null.

---

### `encounters`

```sql
CREATE TABLE encounters (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id            UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    external_encounter_id VARCHAR(64),         -- MIMIC-IV hadm_id
    admit_time            TIMESTAMPTZ,
    discharge_time        TIMESTAMPTZ,
    los_hours             NUMERIC(8, 2),       -- Computed: (discharge - admit) in hours
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_encounters_patient_id ON encounters(patient_id);
```

---

### `icd_codes`

```sql
CREATE TABLE icd_codes (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    encounter_id UUID NOT NULL REFERENCES encounters(id) ON DELETE CASCADE,
    code         VARCHAR(16) NOT NULL,
    description  TEXT,
    code_type    VARCHAR(8) NOT NULL,          -- 'ICD-9' | 'ICD-10'
    is_primary   BOOLEAN NOT NULL DEFAULT false,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_icd_codes_encounter_id ON icd_codes(encounter_id);
CREATE INDEX idx_icd_codes_code ON icd_codes(code);
```

---

### `documents`

```sql
CREATE TABLE documents (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id    UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    encounter_id  UUID REFERENCES encounters(id) ON DELETE SET NULL,
    document_type VARCHAR(64) NOT NULL,        -- 'discharge_summary' | 'progress_note' | 'radiology_report' | ...
    source        VARCHAR(32) NOT NULL,        -- 'upload' | 'mimic_demo' | 'mimic_note' | 'synthetic'
    file_name     VARCHAR(256),
    mime_type     VARCHAR(64),                 -- 'application/pdf' | 'image/png' | 'text/plain'
    size_bytes    INTEGER,
    storage_key   VARCHAR(512),                -- 'local:documents/{id}/file.pdf' or 's3:bucket/key'
    status        VARCHAR(32) NOT NULL DEFAULT 'queued',
                  -- 'queued' | 'ocr_processing' | 'extracting' | 'validating' | 'completed' | 'failed'
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_documents_patient_id ON documents(patient_id);
CREATE INDEX idx_documents_encounter_id ON documents(encounter_id);
CREATE INDEX idx_documents_status ON documents(status);
```

**Note:** `source_text` is NOT stored in `documents`. Use `document_versions` instead.

---

### `document_versions`

```sql
CREATE TABLE document_versions (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id    UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL DEFAULT 1,
    raw_text       TEXT NOT NULL,              -- Full extracted/OCR text
    text_hash      VARCHAR(64) NOT NULL,       -- SHA-256 of raw_text for deduplication
    page_count     INTEGER,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, version_number)
);

CREATE INDEX idx_doc_versions_document_id ON document_versions(document_id);
```

**Rationale:** When OCR is re-run or text is corrected, a new version is created.
`evidence_spans` reference a specific `document_version_id` to maintain exact provenance.

---

### `processing_jobs`

```sql
CREATE TABLE processing_jobs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id      UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    pipeline_version VARCHAR(32),              -- 'v1.4.2'
    status           VARCHAR(32) NOT NULL DEFAULT 'queued',
                     -- 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
    started_at       TIMESTAMPTZ,
    completed_at     TIMESTAMPTZ,
    processing_ms    INTEGER,
    error_code       VARCHAR(64),
    error_message    TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_processing_jobs_document_id ON processing_jobs(document_id);
CREATE INDEX idx_processing_jobs_status ON processing_jobs(status);
```

---

### `processing_steps`

```sql
CREATE TABLE processing_steps (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    processing_job_id UUID NOT NULL REFERENCES processing_jobs(id) ON DELETE CASCADE,
    step_name         VARCHAR(64) NOT NULL,
                      -- 'ocr' | 'text_extraction' | 'clinical_extraction'
                      -- | 'normalization' | 'validation' | 'evidence_linking'
    status            VARCHAR(32) NOT NULL DEFAULT 'pending',
                      -- 'pending' | 'running' | 'completed' | 'failed' | 'skipped'
    started_at        TIMESTAMPTZ,
    completed_at      TIMESTAMPTZ,
    processing_ms     INTEGER,
    model_version     VARCHAR(64),             -- e.g. 'claude-sonnet-5 / 2026-09'
    error_message     TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_processing_steps_job_id ON processing_steps(processing_job_id);
```

**This is the data source for the AI Operations → Processing Timeline view.**

---

### `extractions`

```sql
CREATE TABLE extractions (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id       UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    processing_job_id UUID REFERENCES processing_jobs(id) ON DELETE SET NULL,
    model_name        VARCHAR(128),            -- 'claude-sonnet-5'
    model_version     VARCHAR(64),             -- '2026-09'
    status            VARCHAR(32) NOT NULL DEFAULT 'pending',
                      -- 'pending' | 'completed' | 'failed'
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_extractions_document_id ON extractions(document_id);
```

---

### `clinical_entities`

```sql
CREATE TABLE clinical_entities (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    extraction_id    UUID NOT NULL REFERENCES extractions(id) ON DELETE CASCADE,
    entity_type      VARCHAR(32) NOT NULL,
                     -- 'diagnosis' | 'medication' | 'symptom' | 'procedure'
                     -- | 'lab_result' | 'temporal'
    raw_text         TEXT NOT NULL,            -- Original extracted text
    normalized_value TEXT,                     -- Normalized/standardized value
    confidence       NUMERIC(5, 4) NOT NULL,   -- 0.0000 – 1.0000
    status           VARCHAR(32) NOT NULL DEFAULT 'unreviewed',
                     -- 'unreviewed' | 'approved' | 'rejected' | 'needs_correction'
    details          JSONB,                    -- Entity-type-specific fields (dose, code, etc.)
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_clinical_entities_extraction_id ON clinical_entities(extraction_id);
CREATE INDEX idx_clinical_entities_entity_type ON clinical_entities(entity_type);
CREATE INDEX idx_clinical_entities_status ON clinical_entities(status);
```

**`details` JSONB examples by entity type:**

```json
// diagnosis
{ "code": "J44.1", "code_system": "ICD-10", "status": "Active", "chronicity": "Chronic" }

// medication
{ "dose": "500 mg", "frequency": "Once daily", "route": "Oral", "interaction_flag": true }

// lab_result
{ "value": "7.2", "unit": "mmol/L", "reference_range": "3.5-5.0", "is_abnormal": true }
```

---

### `evidence_spans`

```sql
CREATE TABLE evidence_spans (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id           UUID NOT NULL REFERENCES clinical_entities(id) ON DELETE CASCADE,
    document_version_id UUID NOT NULL REFERENCES document_versions(id),
    page_number         INTEGER,
    start_offset        INTEGER NOT NULL,      -- Character offset in raw_text
    end_offset          INTEGER NOT NULL,      -- Character offset in raw_text
    text                TEXT NOT NULL,         -- The exact span text
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_evidence_spans_entity_id ON evidence_spans(entity_id);
```

**This is the data source for the Evidence Panel — "View Source" button in Clinical Workspace.**

One entity can have multiple evidence spans (e.g., a diagnosis mentioned in two sections).

---

### `validation_results`

```sql
CREATE TABLE validation_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id       UUID NOT NULL REFERENCES clinical_entities(id) ON DELETE CASCADE,
    validation_rule VARCHAR(128) NOT NULL,
                    -- 'schema_validation' | 'required_fields' | 'evidence_required'
                    -- | 'confidence_threshold' | 'terminology_normalization'
    status          VARCHAR(16) NOT NULL,      -- 'pass' | 'fail' | 'warning'
    severity        VARCHAR(16),               -- 'info' | 'warning' | 'error'
    message         TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_validation_results_entity_id ON validation_results(entity_id);
```

---

### `review_tasks`

```sql
CREATE TABLE review_tasks (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id  UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    entity_id    UUID REFERENCES clinical_entities(id) ON DELETE SET NULL,
    priority     VARCHAR(16) NOT NULL DEFAULT 'normal',
                 -- 'high' | 'medium' | 'normal'
    reason       TEXT,                         -- Why this was flagged for review
    status       VARCHAR(32) NOT NULL DEFAULT 'pending',
                 -- 'pending' | 'in_review' | 'approved' | 'rejected' | 'needs_correction'
    assigned_to  UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at   TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    decision     VARCHAR(32),                  -- 'approved' | 'rejected' | 'corrected'
    comment      TEXT
);

CREATE INDEX idx_review_tasks_status ON review_tasks(status);
CREATE INDEX idx_review_tasks_priority ON review_tasks(priority);
CREATE INDEX idx_review_tasks_entity_id ON review_tasks(entity_id);
```

---

### `users`

```sql
CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         VARCHAR(256) UNIQUE NOT NULL,
    display_name  VARCHAR(128),
    role          VARCHAR(32) NOT NULL DEFAULT 'reviewer',
                  -- 'admin' | 'clinician' | 'reviewer' | 'viewer'
    is_active     BOOLEAN NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Note:** No password hash in Phase 2 (localhost-only, no auth). JWT middleware
will be added in D10. The `users` table is created now so `review_tasks.assigned_to`
and `audit_events.user_id` can reference it.

---

### `audit_events`

```sql
CREATE TABLE audit_events (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID REFERENCES users(id) ON DELETE SET NULL,
    action        VARCHAR(64) NOT NULL,
                  -- 'view_document' | 'approve_entity' | 'reject_entity'
                  -- | 'edit_entity' | 'upload_document' | 'run_extraction'
    resource_type VARCHAR(64),                 -- 'document' | 'entity' | 'review_task'
    resource_id   UUID,
    metadata      JSONB,                       -- Any additional context
    ip_address    VARCHAR(45),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_events_user_id ON audit_events(user_id);
CREATE INDEX idx_audit_events_resource ON audit_events(resource_type, resource_id);
CREATE INDEX idx_audit_events_created_at ON audit_events(created_at);
```

---

## Migration Order (Alembic)

```
001_create_users.py
002_create_patients_encounters_icd.py
003_create_documents_versions.py
004_create_processing_jobs_steps.py
005_create_extractions_entities_spans.py
006_create_validation_results.py
007_create_review_tasks.py
008_create_audit_events.py
```

---

## Provenance Trace Example

```
Diagnosis: "Community-Acquired Pneumonia"
 │
 ├── clinical_entities.id = "entity-abc"
 │     normalized_value: "Community-Acquired Pneumonia"
 │     confidence: 0.6420
 │     details: { "code": "J18.9", "code_system": "ICD-10", "status": "Possible" }
 │
 ├── extractions.id = "extract-xyz"
 │     model_name: "claude-sonnet-5"
 │     model_version: "2026-09"
 │
 ├── processing_jobs.id = "job-001"
 │     pipeline_version: "v1.4.2"
 │
 ├── document_versions.id = "docver-001"
 │     version_number: 1
 │     document_id: "doc-001"
 │
 └── evidence_spans.id = "span-001"
       start_offset: 482
       end_offset:   512
       text: "possible community-acquired pneumonia"
       page_number: 1
```
