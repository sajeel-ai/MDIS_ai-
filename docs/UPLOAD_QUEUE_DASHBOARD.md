# Upload, queue, and dashboard

## Run the application

Use the configured local environment and a PostgreSQL database dedicated to this checkout. The checked-in local backend configuration currently resolves to `cognate_ai`; do not use it for DB-backed tests. For an isolated local run, start disposable PostgreSQL in Docker:

```powershell
docker run --rm --name mdis-upload-test-db -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=mdis_test -p 5433:5432 postgres:16
```

In a second PowerShell terminal from the repository root, point the app at that database, apply migrations, and start both servers:

```powershell
$env:DATABASE_URL = 'postgresql+asyncpg://test:test@localhost:5433/mdis_test'
Set-Location backend
..\venv\Scripts\python.exe -m alembic upgrade head
Set-Location ..
npm run dev
```

The existing Vite development server can also be used through the preview panel. Set `VITE_API_BASE_URL` only when the API is not proxied at `/api/v1`.

The three-pane review workspace remains off by default. To enable it in a local frontend session, set `VITE_ENABLE_REVIEW_WORKSPACE=true` before starting Vite. Restart Vite after changing Vite environment variables. The old review route remains available when the flag is off.

To enable the workspace in the PowerShell startup above, run `$env:VITE_ENABLE_REVIEW_WORKSPACE = 'true'` after `Set-Location ..` and before `npm run dev`. Leave it unset to keep the existing review screen active.

## Upload and patient linking

The upload form accepts one PDF, PNG, JPG/JPEG, TIFF, or TXT file. The browser checks size and file signature; the API repeats size/signature checks and attempts to decode images/PDFs. Unsupported types, mismatched signatures, and unreadable files return clear errors. Multi-file upload is not implemented. Search existing patients from the upload form; the search uses the authenticated POST `/api/v1/search` body, so patient terms do not enter the URL. The current API has no patient-create endpoint. Upload without a patient is allowed, and the document list continues to show that approval is blocked until a patient is linked.

The actual processing job and step records drive the progress display. OCR quality score is not available per document. The backend does not report a separate section-finding stage, so the UI says so instead of estimating it. Failed jobs can be retried through the existing retry endpoint.

## Environment variables

- `DATABASE_URL`: PostgreSQL connection for this app. Use a disposable database ending in `_test` for test runs; never point tests at `cognate_ai`.
- `MAX_UPLOAD_SIZE_BYTES`: backend upload limit; defaults to 25 MiB.
- `MAX_DOCUMENT_PAGES`: backend page limit.
- `VITE_MAX_UPLOAD_SIZE_BYTES`: optional client-side upload limit; keep it equal to the server limit.
- `VITE_API_BASE_URL`: optional API base; defaults to `/api/v1`.
- `VITE_ENABLE_REVIEW_WORKSPACE`: `true` enables the new review workspace, default `false`.

## Migrations and checks

This upload/queue/dashboard change adds no database migration. The additive document response field `patient_id` is sourced from the existing nullable `Document.patient_id` column. For an existing deployment, run `alembic current` and `alembic upgrade head` from `backend/` if that deployment has pending migrations from earlier work.

## Test commands

Frontend: `npm run typecheck` and `npm run test` from the repository root.

Backend: from `backend/`, set `DATABASE_URL` to a disposable PostgreSQL database whose name ends in `_test`, then run:

```powershell
$env:DATABASE_URL = 'postgresql+asyncpg://test:test@localhost:5433/mdis_test'
..\venv\Scripts\python.exe -m alembic upgrade head
..\venv\Scripts\python.exe -m alembic current
..\venv\Scripts\python.exe -m alembic check
..\venv\Scripts\python.exe -m pytest -q
```

The pytest session guard refuses other database names. The queue-ordering and dashboard-scope unit tests can run without a live connection, but the full upload, permission, audit, and pipeline tests require the migrated disposable PostgreSQL database.

## Known limitations

- Multi-file upload and patient creation are not available.
- Per-document OCR quality scores and a separate section-detection progress signal are not produced by the backend.
- The processing worker runs as FastAPI background work in the API process; durable recovery after process restart is not provided by this flow.
- Dashboard counts, confidence summaries, and recent cases are restricted to the authenticated organization and the dashboard read is audited. Confidence is explicitly labeled uncalibrated model confidence, not extraction accuracy. No labelled evaluation set is available in this feature.
- Patient creation is not available in the current API; reviewers can search and link existing patients. The document list offers linking from its loaded patient list.
- A complete database-backed upload-to-approval journey, including persisted reviewer actions, authorization, and audit rows, still needs to run against the disposable PostgreSQL test database.
- Workflow editing and manual pipeline execution are unavailable; their unsupported controls were removed. EHR push remains visibly labeled Simulation when simulation mode is active.

This workflow is not clinically ready. It still needs a real de-identified evaluation corpus, security review, and compliance review before broader use.
