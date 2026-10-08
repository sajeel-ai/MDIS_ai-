# Cognate AI Website Audit

**Audit date:** 2026-10-05  
**Scope:** React/Vite frontend, FastAPI/SQLAlchemy/PostgreSQL backend, document upload and processing, OCR/extraction, validation/review, FHIR projection, settings/operations pages, and responsive source behavior.  
**Method:** Source inspection and route/data-flow tracing. This is a code audit, not a live penetration test or clinical evaluation. I did not run a browser/device matrix, connect to a live PostgreSQL instance, exercise the running app, run the test suites again, or push to an external FHIR server for this report. Test/build results below are the latest recorded results from the preceding implementation work and are identified as such.

## Executive assessment

The repository now contains an end-to-end prototype workflow: authenticated users can upload documents, process them through OCR and extraction, inspect evidence, review entities, and request a FHIR-shaped document bundle. Several prior gaps have been addressed in code, including organization-scoped ORM reads, upload limits/signature checks, strict extraction models, evidence alignment, validation rules, configurable review policy, and a Composition-first bundle.

The highest-priority remaining concern is **provider correctness**: the configured Azure OCR provider currently returns the literal text `Azure extracted text placeholder`, so selecting it can create a completed-looking workflow with fabricated source text. Do not select this provider until it returns the actual operation result or fails closed.

Other material gaps:

- Background processing runs inside the FastAPI request process, without a durable worker. A restart can leave queued/running work stranded.
- The local extractor is a hand-maintained terminology/regex prototype. Its confidence values are fixed by code and uncalibrated; the synthetic evaluation report is not evidence of performance on real documents.
- The FHIR projection is structurally improved, but normal extraction persistence does not mark codes as verified or persist lab quantity details. Exports therefore commonly fall back to text and omit lab values/ranges.
- Operations/workflow UI includes static status and explanatory placeholders mixed with real API data. Users can mistake display scaffolding for observed system health or executable workflow configuration.
- The ORM organization filter is a central security control. Most protected API flows set session scope after authentication, but several services/routes do not repeat explicit organization filters. Scope is skipped when a session has no organization ID and is not database row-level security; this needs dedicated bypass and cross-organization tests.

No source changes were made during this audit. This document replaces the prior audit, whose descriptions of authentication, extraction validation, upload handling, FHIR ordering, and migration head were stale.

## Severity-ranked findings

### P1 — Azure OCR can persist placeholder text

`backend/app/providers/ocr/azure.py` submits an analyze request, makes one GET request without reading or checking the result, exits the poll loop, and returns the constant `Azure extracted text placeholder`. If this provider is enabled, downstream extraction and review are based on that string rather than OCR output. The provider should poll until a terminal status, parse actual content, enforce timeout/error handling, and fail the job if no result is available. Until fixed, keep Azure OCR disabled.

### P1 — ORM tenant scoping is implicit and fail-open without session context

`backend/app/security/auth.py` sets `db.info["organization_id"]` after resolving the active user. `backend/app/db.py` adds organization criteria to ORM `SELECT`s for users, patients, documents, audit events, jobs, review tasks, extractions, entities, and related rows. Explicit access helpers in `backend/app/security/authorization.py` also constrain documents/patients and return not-found for inaccessible records. These controls mean the old audit's blanket claim that ordinary authenticated document requests are unscoped was incorrect.

However, `apply_organization_scope` returns without adding any criteria if `organization_id` is absent. The mechanism only applies to ORM reads; it is not database row-level security and should not be the only protection around raw SQL, bulk mutations, background tasks, scripts, or future endpoints. Some routes/services (notably audit/dashboard/AI Ops/review/job status) rely on this global listener instead of expressing the scope locally. Add tests proving every protected endpoint returns only its caller's organization, and make request/session scope fail closed for protected data access. Verify background jobs establish the same organization context before querying.

### P1 — In-process background jobs are not durable

`backend/app/routers/documents.py` schedules processing with FastAPI `BackgroundTasks`; `backend/app/services/processing/job_service.py` persists job records and supports retry/idempotency, but no independent worker queue is present in the inspected path. Process termination during OCR/extraction can leave a job in queued/running state indefinitely. Add a durable worker/lease/recovery strategy before relying on long-running workloads.

### P1 — External provider data handling needs an explicit deployment decision

The OpenAI extraction provider sends document text to an external API when configured (`backend/app/providers/extraction/openai.py`). The code audit does not establish contractual, deployment, or data-processing controls. Keep external providers disabled until the data flow and applicable handling requirements are reviewed; never use real patient data in the current synthetic evaluation harness.

### P1 — FHIR projection drops code/value detail from ordinary workflow output

`backend/app/services/fhir/fhir_service.py` emits a Composition-first `Bundle.type="document"`, UUID fullUrls, references, patient gender normalization, supported resource types, and provenance. It only emits a terminology `coding` when `details.code_verified is True`. But `backend/app/workflows/clinical_processing.py` persists `code` and `code_system` without `code_verified`, so the ordinary extraction workflow does not produce that condition. The FHIR service also reads lab `value`, `unit`, `unit_code`, and `reference_range`, and medication `explicit_prescription`; the workflow persistence shown does not populate those fields. As a result, normal data commonly exports concepts as text and labs without valueQuantity/reference ranges; MedicationRequest selection is also unavailable unless another path supplies the field. Either persist validated structured details with provenance or remove the unsupported promise from the export contract.

The code uses `fhir.resources.R4B` model validation plus custom bundle checks. `.github/workflows/ci.yml` is configured to run the official HL7 validator against synthetic bundles, but CI has not been observed green in this audit. Local Java-based HL7 validation and an external test-server push were not run. Do not describe the result as EHR-ready or interoperable.

### P2 — Local extraction is narrow and confidence is not calibrated

`backend/app/providers/extraction/local.py` uses a finite term dictionary and regular expressions. It can miss synonyms, ambiguous mentions, table structures, uncommon entities, and spelling/OCR errors. Context rules in `backend/app/providers/extraction/context.py` are deterministic phrase/scope rules, not a general clinical language model; their results need careful review.

Local confidence is assigned by fixed code values rather than calibrated against a held-out real-world set. UI wording now correctly says **Model confidence (uncalibrated)**. The current report at `backend/app/evals/latest_eval.json` is measured on 32 synthetic fixtures; its perfect fixture scores measure only those fixtures and do not establish clinical accuracy or generalization. `backend/app/evals/run_eval.py` calculates assertion accuracy over matched entity keys, so missed/unmatched entities do not contribute to that assertion denominator. Treat all evaluation results as synthetic regression checks only.

### P2 — Some operational status is illustrative rather than observed

- `src/views/AIOperations.tsx` contains a static pipeline-node list whose status is shown as healthy; these cards are not a live per-provider/per-stage health probe.
- AI Operations combines live API metrics/jobs with a synthetic evaluation report. A missing metric (`null`) should remain visibly “Not measured,” not be read as zero or a health signal.
- `src/views/OperationalViews.tsx` Pipeline and Analytics views reuse AI Operations endpoints. Health is derived from available job/metric signals, not independent checks of OCR, extraction, storage, database, and worker readiness.
- `src/pages/Integrations.tsx` performs a real FHIR `/metadata` check when configured, but API/database/pipeline cards are not all independent connection probes.
- `src/pages/Settings.tsx` exposes review policy, while user/role and alert areas are placeholders. Retention statements and security cards should be treated as informational unless backed by enforceable configuration and operational checks.

### P2 — Several page actions are informational or bounded

- `src/pages/Workflows.tsx` draws a fixed workflow. Create/test/configure controls show messages or placeholders; they do not define and execute user-configured pipelines.
- `src/views/Placeholders.tsx` presents AI Extraction as a route hub; extraction itself is driven from document processing rather than configured on that page.
- `src/views/Dashboard.tsx` is backed by dashboard API data, but shortcuts/actions should be checked individually; some are informational navigation rather than export/process actions.
- `src/pages/Documents.tsx` requests the first 50 documents; a search/filter over those loaded results does not make older pages discoverable because there is no visible pagination control. Uploads are automatically queued for processing. Polling is client-side and needs a visible terminal error state/recovery path for all failure cases.
- `src/views/ReviewCenter.tsx` is connected to the review API. The backend queue intentionally limits eligible rows to documents whose `source` is `UserUpload` or `upload` (`backend/app/services/review/review_service.py`); imported/seed data with other source labels will not appear. Queue counts are entity tasks while some summary cards aggregate by document, so numbers can differ without indicating missing records.
- `src/views/PatientTimeline.tsx` displays actual timeline results but only renders four patient selector entries and fetches a bounded patient list; a patient beyond that subset is not selectable from the current control.

### P2 — Navigation state is not URL-backed

`src/App.tsx` switches pages and stores selected document/review IDs in React state. Direct deep links, refresh restoration, and browser back/forward navigation are therefore limited. Replacing a page independently is possible at the component level, but current pages depend on shared `onNavigate` callbacks and API response contracts.

## Page inventory

| Page/view | Current role | Data and workflow observations |
|---|---|---|
| Dashboard | Documents/review summary and shortcuts | Live `/dashboard`; counts and confidence aggregates are data-backed. Confidence is not accuracy. Recent list is bounded. |
| Documents | Upload, search, status, processing/retry, case navigation | Live document/patient/upload/job APIs. First page is bounded to 50; no paging UI. Wide table uses horizontal scrolling. |
| Clinical Workspace | Source text, entity categories, evidence, validation and pipeline | Live document/extraction data. It displays OCR text, not a rendered original file. Category tabs use horizontal scrolling; later tabs can sit offscreen on narrow screens. |
| Review Center | Queue, entity-level decisions, evidence/source context | Live queue, stats, task detail and decision endpoints. Source filter excludes non-upload-origin documents. Queue/detail totals may count different units. |
| AI Extraction | Entry point to upload/workspace/review/operations | Static navigation hub; does not run extraction directly. |
| AI Operations | Job/metrics/evaluation overview | Live API data mixed with fixed stage cards and synthetic fixture results. |
| Data Pipeline | Pipeline status and jobs | Reads AI Ops endpoints; no independent worker/provider diagnostics. |
| Clinical Timeline | Patient clinical event view | Live patient/timeline data with bounded patient selection and event loading. |
| Analytics | Processing aggregates | Live AI Ops metrics; limited to backend-provided measurements. |
| Audit | Recent audit activity | Reads audit endpoint. Audit metadata is ID/action oriented; tenant restriction depends on auth-established ORM scope. |
| Workflows | Visual pipeline map | Fixed diagram; workflow authoring/test controls are placeholders. |
| Integrations | Provider/connection status | FHIR metadata check is real; other status cards are not all independent probes. |
| Settings | Review policy and informational settings | Review policy is read-only/live. Roles and alerts are placeholders; retention/security claims need enforceable backing. |

Shared shell is in `src/layouts/AppLayout.tsx`, navigation in `src/components/navigation/Sidebar.tsx`, top controls in `src/components/navigation/Header.tsx`, and shared fetch/auth behavior in `src/services/api.ts`. The TypeScript API interfaces do not themselves validate runtime payloads.

## Backend workflow and data boundaries

1. **Authentication:** JWT login/current-user flow; roles include admin, clinician, reviewer, viewer, operator. The development bypass is guarded by `import.meta.env.DEV` plus `VITE_AUTH_BYPASS` in the frontend and a backend development-environment guard. The app emits a warning when the frontend bypass is active.
2. **Upload:** chunked write to configured local storage, configured size cap (default 25 MB), extension/signature checks, page-count cap (default 50), sanitized display name and content-hash storage key. Client MIME is not trusted as the validation source. Storage remains local disk in the inspected provider; backup, encryption-at-rest, retention enforcement, malware scanning, and tenant-isolated object storage were not established by this code inspection.
3. **Processing:** job and step records are created; OCR and extraction run through the workflow in the API process. Retry removes partial output from the failed run before recreating work.
4. **OCR:** local Tesseract image/PDF processing and plain-text reading are implemented; image confidence is computed from word-level OCR data, while plain text confidence is null. Tesseract (and PDF rendering dependencies where used) must be installed in the host environment. Azure currently returns placeholder text and is unsafe to select.
5. **Extraction/evidence:** provider candidates pass through a strict Pydantic entity contract; invalid items are rejected with safe reasons. Evidence is checked against the normalized text, with exact-search offset relocation. Unmatched evidence is flagged for review. Assertion/section rules exist but are heuristic.
6. **Validation/review:** rule modules generate coded validation results; default review policy is `all`, and threshold policy still forces review for validation issues, non-present assertions, medications, and low confidence. Decisions preserve the original AI value and are audited.
7. **Export:** FHIR document projection filters to approved, present entities by default; optional unreviewed entities are marked unconfirmed. Current structured-detail persistence gaps limit codes and lab quantities as described above. Outbound FHIR push is disabled by default and guarded for configured test use.

Migrations run through **016** (not 011): tenant/role scope, append-only audit protections, assertion/evaluation support, validation results and review policy were added after the original audit. Current schema/model contracts should continue to be checked together when changing entity or export fields.

## Responsive source audit (not device verified)

This section is based on source classes and previous user screenshots, not a fresh visual run at each viewport.

| Area | Source behavior | Risk/verification need |
|---|---|---|
| App shell/sidebar | Mobile drawer below `md` (768px); collapsed sidebar at tablet widths; expanded from `lg` (1024px). Main content has responsive padding and horizontal overflow containment. | Confirm drawer width, landscape height, safe-area footer, focus/escape behavior in a browser. Current spec documentation does not exactly match these breakpoints. |
| Documents/Dashboard tables | Horizontal-scroll wrappers; tables preserve a minimum width rather than compressing columns. | Table-local horizontal scrolling is expected. Check that it does not create whole-page horizontal overflow and that action columns remain reachable. |
| Clinical Workspace | Source/entity mobile panel switch; tab strip uses `overflow-x-auto`. | Pipeline and later clinical tabs may require horizontal swipe; this was visible in a user screenshot. Consider scroll affordance/active-tab reveal. |
| Review Center | Mobile queue/detail flow stacks; desktop uses internal panels. | Long review form depends on page scrolling; validate bottom actions, keyboard focus and scroll ownership on phone and tablet. |
| Timeline | Patient selector and event filters scroll horizontally; selector renders first four patients. | Later patients are not exposed by current selector; verify overflow affordance. |
| Workflows | Nodes stack below `lg`; connectors hidden below `lg`. | Mobile sequence no longer visibly reads as a connected workflow; controls do not execute a configured workflow. |
| Global scrolling | Main shell and selected pages/panels each use overflow rules; global scrollbar is thin and blue. | Test nested touch scrolling and ensure no clipped lower content. Source inspection cannot establish actual scroll behavior. |

Suggested manual viewport set: 360×800, 390×844, 430×932, 768×1024, 1024×768, 1366×768, 1440×900, and 844×390 landscape. Check browser zoom, keyboard-only use, drawer/backdrop, tab reachability, table scroll, long review forms, and API-down states. This matrix was **not run**.

## Replaceability and coupling

- Static hub/diagram sections (`AI Extraction`, `Workflows`, placeholder Settings sections) are comparatively easy to replace at the UI layer.
- Documents, Clinical Workspace, Review Center, Timeline, Dashboard and operations views depend on API shape, identifiers, lifecycle states, and shared navigation callbacks. Replace those in coordination with the API contract or preserve adapters.
- OCR/extraction/storage providers have provider interfaces, so implementations can be swapped, but provider factories/config, data policy, tests, and error semantics must move together. The Azure provider needs correction before it qualifies as a usable implementation.
- FHIR projection is a backend boundary but depends on extraction detail fields and review-state semantics. Improve that data contract before treating an external FHIR consumer as a drop-in replacement.
- In-memory page selection is the main navigation limitation for independent page replacement and shareable work items; stable routes would make page boundaries clearer.

## Verification status

The following results were recorded in the preceding implementation work; they were **not rerun for this audit**:

- Backend: `python -m pytest tests -q` — **112 passed**.
- Frontend: `npm run check` — TypeScript check and lint completed, **18 frontend tests passed**, and Vite production build completed. Vite printed a config-loader warning about `__dirname`/JSON imports; it did not fail the build.
- FHIR: local official HL7 validator was not run because Java was unavailable. CI workflow is configured to run it on synthetic bundles, but no CI result was inspected here.
- Runtime: no live API/PostgreSQL request, browser console check, device viewport check, or TEST FHIR server push was performed for this audit.

## Recommended remediation order

1. Disable Azure OCR until it parses the completed operation response and add tests for success, pending, failure, truncation, and timeout.
2. Add organization-scope tests for every protected list/detail/mutation route, including audit, dashboard, AI Ops, review and processing jobs; make missing request org scope fail closed and verify worker context.
3. Add a durable background worker/recovery mechanism and a user-visible stuck-job recovery state.
4. Make extraction persistence carry only verified code mappings and validated lab/medication details needed by FHIR; add fixtures proving the persisted data produces expected resource fields.
5. Keep synthetic evaluation clearly labeled, repair metric denominators for assertion/missed entities, and expand carefully curated fixtures before using the harness as a regression gate.
6. Replace fixed “healthy” stage cards with observed status or label them as a diagram; distinguish null/unavailable metrics from zero.
7. Add pagination or explicit “first N”/load-more behavior to Documents and Timeline selectors; add clear horizontal-scroll affordances for clinical tabs and wide tables.
8. Run manual responsive QA and inspect browser console/network behavior with the real backend and a synthetic dataset; record actual viewport results.
