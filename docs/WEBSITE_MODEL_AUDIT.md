# MDIS Website and Document Model Audit

**Review date:** 2026-10-11  
**Scope:** frontend request flow, document workflow, account-request flow, FHIR export, and SQLAlchemy document models.  
**Method:** static inspection of the current source tree. Runtime endpoint tests were not used for this report because the local Vitest/build environment is currently blocked by the Tailwind native module (`spawn EPERM`) and the backend test environment has PostgreSQL/pytest temporary-directory failures.

## Executive summary

The main document workflow is coherent:

1. Upload a document.
2. Start extraction automatically.
3. Inspect extracted text and entities.
4. Review each flagged entity.
5. Approve or correct all review tasks.
6. Export or push the approved FHIR Bundle.

The largest usability issue found is that the account-request organization selector can display many duplicate synthetic organizations. The application also makes several requests that are useful but can feel redundant to users because they run before the related panel is opened.

## Requests that are useful and should remain

| Request | Caller | Purpose |
| --- | --- | --- |
| `GET /api/v1/documents` | Documents page | Master document list, filters, pagination |
| `GET /api/v1/patients` | Documents page | Upload form patient selector |
| `POST /api/v1/documents/upload` | Upload form | Stores the source document |
| `POST /api/v1/documents/{id}/process` | Upload form | Starts extraction |
| `GET /api/v1/review/queue` | Review Center | Loads review tasks |
| `GET /api/v1/review/stats` | Review Center | Dashboard counters for review status |
| `GET /api/v1/review/{task_id}` | Review detail | Loads source text and evidence |
| `GET /api/v1/integrations/fhir/metadata` | Approved Files | Checks configured FHIR R4 server |
| `GET /api/v1/documents/{id}/fhir` | FHIR download | Generates an audited FHIR Bundle |
| `POST /api/v1/integrations/fhir/push/{id}` | FHIR test push | Opt-in synthetic-only push |

## Redundant or wasteful requests

### 1. Patient list loads on every Documents refresh

`Documents.tsx` calls `fetchDocuments` and `fetchPatients` together every time the page loads or filters change. The patient list is needed only when the upload modal is opened.

**Impact:** unnecessary patient PHI is fetched and rendered in memory on every document filter change.  
**Recommendation:** load patients when the upload modal opens, cache the result for that session, and keep the document query independent.

### 2. Review queue and review stats are fetched together for every filter change

The Review Center reloads both the queue and aggregate stats whenever status or priority changes. This is functionally correct, but the stats do not depend on the selected queue filters.

**Impact:** repeated aggregate queries during ordinary queue navigation.  
**Recommendation:** load stats on entry and refresh them after a decision; reload only the queue when a filter changes.

### 3. Approved Files loads the complete review queue

`ApprovedFiles.tsx` requests up to 100 review tasks solely to build a document-to-task map for the Review Center link.

**Impact:** unnecessary task and entity data for an approved-file list.  
**Recommendation:** add a small server response containing the review record ID for each approved document, or make the review link document-scoped.

### 4. FHIR metadata is requested for every Approved Files load

This request is useful for the connection card, but it is independent of the approved-document list.

**Recommendation:** cache the result briefly and refresh it only when the user clicks Refresh or when the Integrations page is opened.

## Account-request data quality finding

The registration form loads organization names from `GET /api/v1/auth/config`. The screenshot shows repeated entries such as `Synthetic tenant A` and many synthetic organizations with UUID suffixes.

This is not a frontend rendering defect: the selector is displaying duplicate organization records returned by the backend.

**Recommended fix:** seed synthetic organizations idempotently and return a de-duplicated organization list (`organization_id` as the key). Do not merge organizations solely by display name in production, because two real organizations may legitimately share a name.

## Document model audit

### Current model relationships

- `Document` owns versions, processing jobs, extractions, and review tasks.
- `DocumentVersion` stores versioned source text and provenance.
- `Extraction` owns `ClinicalEntity` records.
- `ClinicalEntity` owns evidence spans and validation results.
- `ReviewTask` records the human decision for an entity.
- `Patient` and `Document` are organization-scoped.

### Findings

1. `Document.patient_id` is declared non-nullable, while several UI states display “Patient not linked.” The data contract and UI state should be reconciled. If unlinked documents are supported, the column and API must explicitly allow `NULL`; otherwise the UI should never advertise that state.
2. `ReviewTask` has no explicit document-version foreign key. Re-extraction must archive or supersede old tasks to preserve which version was approved.
3. `Document` stores processing and review status separately, which is correct, but every list and export must use the shared lifecycle derivation. Directly checking only `review_status` can show stale approvals.
4. FHIR bundle status is currently generated on demand rather than persisted per document version. This prevents reliable display of generated, stale, pushed, or failed state.
5. `ClinicalEntity.details` is JSONB and intentionally flexible, but medication dose, unit, frequency, and lab reference ranges need schema-level validation tests because they drive FHIR output.

## Document workflow gaps to address

- Show a document-level progress summary such as `3 of 5 findings reviewed`.
- Make the distinction between **Inspect** and **Review** explicit in every document row.
- Disable or explain FHIR download when a required patient link is missing.
- Show the exact safe reason for a failed FHIR push, especially when `FHIR_PUSH_ENABLED=false`.
- Add a document-level review endpoint or a document-scoped review route so users do not need to infer that every task must be completed.

## Security and authorization notes

- Do not remove organization filters from any new document, patient, finding, review, or audit query.
- Do not place patient names, MRNs, or search text in shareable URLs.
- Keep FHIR pushes disabled by default and restricted to synthetic/test documents.
- Keep the existing audit event for upload, review decisions, FHIR downloads, and push attempts.

## Not changed by this audit

This report does not change application behavior, database schema, authorization, tenant isolation, or audit handling. It is an audit artifact for prioritizing the next implementation stage.
