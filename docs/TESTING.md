# Local checks

Use the Node version in `.nvmrc` for frontend commands.

```powershell
npm ci
npm run check
```

The frontend check runs TypeScript, the existing Oxfmt check for frontend test sources, Vitest, and a production Vite build. This repository does not currently configure ESLint or another code linter.

Run backend tests from the backend directory with PostgreSQL running and the schema migrated:

```powershell
cd backend
alembic upgrade head
pytest -q
```

The backend test fixtures set authentication mode explicitly and route temporary OCR files and local storage into isolated pytest temporary directories. CI provisions PostgreSQL and OCR command-line tools before running these commands.
