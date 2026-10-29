# Backend test environment

## Required

- `DATABASE_URL`: PostgreSQL connection URL whose database name ends in
  `_test`. The backend root `conftest.py` refuses all other database names
  before pytest runs. Use a disposable database, for example
  `postgresql+asyncpg://test:test@localhost:5433/mdis_test`.

## Test-only default

- `STORAGE_ENCRYPTION_KEY`: pytest sets a synthetic key with
  `os.environ.setdefault` only when the resolved `DATABASE_URL` database
  name ends in `_test`. An explicitly supplied value is preserved. This
  default exists only in `backend/conftest.py`; application code still
  requires a configured key. The missing-key security test clears the
  environment value and settings with `monkeypatch` and verifies rejection.

## Optional integrations and tools

- `FHIR_VALIDATOR_JAR` and Java on `PATH`: enable the two official FHIR
  validator integration tests. They skip when either is unavailable.
- `MDIS_MAILPIT_E2E=1` and `MAILPIT_URL` (defaults to
  `http://127.0.0.1:8025`): enable the Mailpit authentication end-to-end test.
  Its SMTP configuration must also be set in the backend settings:
  `EMAIL_PROVIDER=smtp`, `SMTP_HOST`, and the applicable `SMTP_PORT`,
  `SMTP_USER`, `SMTP_PASSWORD`, and `SMTP_STARTTLS` values.
- Tesseract on `PATH`: required for local OCR tests; unit tests that do not
  invoke local OCR do not need it.
- `PYTEST_TIMEOUT`: optional pytest-timeout override, in seconds. The plugin
  is pinned in `requirements.txt`; use `--timeout=<seconds>` to set a
  per-command timeout.

## Run

From `backend/`, install the pinned test dependencies and run the suite:

```powershell
python -m pip install -r requirements.txt
$env:DATABASE_URL = "postgresql+asyncpg://test:test@localhost:5433/mdis_test"
python -m pytest -q
```

Never point tests at the development database `cognate_ai`.
