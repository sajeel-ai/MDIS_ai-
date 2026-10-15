# Backend test database setup

The backend test suite uses the PostgreSQL URL from `backend/.env`:

```text
postgresql+asyncpg://cognate:<password>@127.0.0.1:5432/cognate_ai
```

Start PostgreSQL before running pytest. On Windows, use the installed PostgreSQL
service (the service name varies by version), for example from an elevated
PowerShell:

```powershell
Get-Service *postgres*
Start-Service postgresql-x64-16   # use the service name shown above
```

Verify the database is accepting connections:

```powershell
Test-NetConnection 127.0.0.1 -Port 5432
cd "C:\Users\Meta\project z\Cognate-AI main\Cognate-AI\backend"
.\venv\Scripts\python.exe -c "import asyncio, os, asyncpg; from urllib.parse import urlparse; u=urlparse(os.environ['DATABASE_URL'].replace('postgresql+asyncpg','postgresql')); asyncio.run(asyncpg.connect(host=u.hostname, port=u.port or 5432, user=u.username, password=u.password, database=u.path.lstrip('/'))); print('PostgreSQL connection OK')"
```

If `DATABASE_URL` is not already loaded, load `backend/.env` or set it explicitly
before the probe. The previous failures showed `ConnectionRefusedError` and
`WinError 1225` while asyncpg attempted `127.0.0.1:5432`; they are database
startup/connectivity failures, not tests to skip.

Then run with `$env:DEBUG='false'`:

```powershell
$env:DEBUG='false'
.\venv\Scripts\python.exe -m pytest tests --timeout=60 -q
```

## Mandatory environment flag: `DEBUG=false`

In this environment/sandbox, `DEBUG` may inherit string values such as `"release"` from system environment variables. Because Pydantic `Settings` strictly validates `debug: bool`, running pytest when `DEBUG` is set to any non-boolean string causes `Settings()` instantiation to raise a `pydantic_core.ValidationError` during `conftest.py` loading, aborting test collection before any tests run.

* **Requirement:** Pytest must always be run with `$env:DEBUG='false'` (or `DEBUG=false`).
* **Rule:** Do not change application code (such as `app/config.py`) to coerce misconfigured `DEBUG` strings. Keep application config strict and pass the explicit flag in test runners.

## Verification and Git History Corrections

* **Correction regarding commit `a849c3e`:** The commit message for `a849c3e` stated "verified in user terminal". This was incorrect; the commit was not run or verified in the user's terminal.
* **Correction regarding explanation citing commit `7d57403`:** An earlier explanation described `7d57403` as "test(extract)..."; this attribution was incorrect.
