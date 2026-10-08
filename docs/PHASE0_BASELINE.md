# Phase 0 Baseline

**Captured:** 2026-10-05  
**Phase:** Baseline only. No application code was changed.

## Repository and configuration

- `git status` could not run: no `.git` repository was found at the project root or checked parent paths.
- Alembic reports migration **016** as both the sole head and current database revision.
- Local provider configuration is OCR `local`, extraction `local`, storage `local`.
- The checked-in local environment has the frontend auth bypass enabled and backend auth disabled, both with `APP_ENV=development`. Keep this configuration local; it is not suitable for a shared or deployed environment. Secret values were not read into this report.
- `package.json` pins Node `22.22.x`; `.nvmrc` specifies `22.22.2`.

## Fresh verification

| Check | Result |
|---|---|
| `python -m pytest tests -q` using PATH Python 3.14 | **Failed during collection:** missing `asyncpg` and `pytest-asyncio`; 14 test modules could not collect. |
| `backend/venv/Scripts/python.exe -m pytest tests -q` | **Failed during setup:** pytest temp-directory access raised Windows `PermissionError` (`WinError 5`). A retry using a workspace basetemp also encountered access errors; pytest then failed during temp cleanup before producing a normal summary. Test bodies were not verified. |
| `npm run check` | **Failed.** TypeScript check passed; formatting/lint passed. Vitest could not load the Windows `@tailwindcss/oxide` native binding and reported `spawn EPERM`. The script stopped before build. |
| `npm run build` | **Failed before app compilation** for the same Tailwind native binding load failure and `spawn EPERM`. |
| `alembic heads` / `alembic current` using backend virtualenv | **Passed:** revision `016 (head)` is current. |

## Baseline blockers

1. Backend tests need a pytest temp path accessible to this Windows execution environment, plus the expected dependencies in the Python used to run tests.
2. Frontend Vitest and build are blocked loading `@tailwindcss/oxide-win32-x64-msvc`; Vite also fails to spawn a helper process with `EPERM`.
3. Git-based change inspection is unavailable because this workspace copy has no `.git` metadata.
4. Pytest's generated `backend/.pytest-phase0-basetemp` directory could not be removed afterward; Windows denied access during cleanup. It contains test-run temporary data, not application source.

No remediation phase has started. Stop here pending approval to continue to Phase 1.
