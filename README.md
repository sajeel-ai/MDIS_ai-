# Cognate AI

## Authentication setup

For local authentication-email testing, see [Authentication email delivery](docs/auth-email-delivery.md). Docker Compose includes Mailpit and requires a root `.env` copied from `.env.example`; the PostgreSQL password has no default.

The API authenticates users with short-lived HttpOnly access cookies and rotating refresh cookies. The browser stores neither token in Web Storage. Unsafe cookie-authenticated requests require the matching CSRF cookie/header pair. The `AUTH_DISABLED` and `VITE_AUTH_BYPASS` flags do not create identities; a backend bypass flag or frontend bypass build flag causes production startup to fail.

1. Copy `backend/.env.example` to `backend/.env` and keep `APP_ENV=development`, `ENVIRONMENT=development`, `DEBUG=false`, and `AUTH_COOKIE_SECURE=false` for local HTTP development. Generate a private local signing key with `python -c "import secrets; print(secrets.token_urlsafe(48))"` and place that value in `JWT_SECRET_KEY` in `backend/.env`.
2. Install backend dependencies, including `argon2-cffi`, and apply migrations from the `backend` directory:

   ```powershell
   .\venv\Scripts\python.exe -m pip install -r requirements.txt
   .\venv\Scripts\alembic.exe upgrade head
   ```

3. Create the first administrator interactively. No default account or password is supplied:

   ```powershell
   .\venv\Scripts\python.exe -m scripts.create_first_admin
   ```

4. Start the backend and frontend, open the local site, and sign in with the credentials entered into the CLI. For production, configure a private `JWT_SECRET_KEY` of at least 32 characters, `AUTH_COOKIE_SECURE=true`, `DEBUG=false`, and production environment variables before starting the API.

   Generate the independent 32-byte MFA-at-rest key and put the output in `AUTH_ENCRYPTION_KEY` (never commit it):

   ```powershell
   python -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
   ```

   Admin and operator accounts must enroll an authenticator before they receive application access. The sign-in screen starts enrollment, renders the `otpauth://` setup value as a local QR code (without sending it to a QR service), and displays recovery codes once after enrollment. Store those recovery codes securely.

## Account recovery and onboarding

Password recovery uses `POST /api/v1/auth/forgot-password`, `POST /api/v1/auth/verify-reset-code`, and `POST /api/v1/auth/reset-password`. The request endpoint returns the same message whether the account exists or not. Registration behavior is controlled by `REGISTRATION_MODE`: `approval` allows verified account requests that remain inactive until an administrator approves them; `invite_only` and `disabled` do not allow public registration. Invitation onboarding uses `POST /api/v1/admin/invitations` and the single-use `POST /api/v1/admin/invitations/accept`.

For a local development account only, if email recovery is unavailable, an operator can reset an existing account from the backend shell. This command refuses non-development environments, applies the normal password policy, writes an ID-only audit event, and revokes existing sessions; it does not create or activate accounts:

```powershell
cd backend
$env:DEBUG = "false"
.\venv\Scripts\python.exe -m scripts.reset_local_password
```

Configure `CORS_ORIGINS` as the comma-separated exact frontend origin allowlist. Wildcard origins are rejected. For email, set `EMAIL_PROVIDER` to `smtp`, `resend`, or `sendgrid`, plus the provider credentials and `EMAIL_FROM`. When email is not configured, invitation responses report `email_delivery: not_configured`; password reset and enabled registration return a global HTTP 503 state. With a provider configured, reset responses remain enumeration-safe and do not disclose account state. Action links are never printed to application logs.

Admin account/session APIs are under `/api/v1/admin/users`. They only operate within the authenticated administrator's organization. Security audit rows record actor, organization, IP, sanitized user-agent, and server-generated request ID; token/password values are not audit metadata.

The browser signs out after 30 minutes without user activity and shows a warning for the final two minutes. To change the idle duration locally, set `VITE_AUTH_INACTIVITY_MINUTES` in the frontend `.env.local` file; the default is 30 minutes. Session/API responses use `Cache-Control: no-store` so authenticated data is not served from browser caches.

An administrator may also create explicitly configured local admin/operator accounts using `COGNATE_DEV_ADMIN_*` and `COGNATE_DEV_OPERATOR_*` values in `backend/.env`, then running `python -m scripts.seed_dev_users` from `backend`. This helper refuses production and uses the same Argon2id hashing and password checks.

## Password blocklist

Passwords are checked against a built-in common-password list and the optional newline-delimited file configured by `PASSWORD_BLOCKLIST_FILE`. Deployments should provide and maintain a locally approved common/compromised-password dataset there. Password changes and provisioning enforce a 12 character minimum, a 1024 character maximum, and rejection of values containing the account email or name; there are no composition rules.

## Security and testing

Copy `backend/.env.example` to `backend/.env`; leave secrets blank until you generate or receive private values. The example contains no working credentials. Provider environment names must match the application settings (`AZURE_DOC_INTEL_ENDPOINT`, `AZURE_DOC_INTEL_KEY`, and `OPENAI_API_KEY`). Keep the mock OCR/extraction providers confined to synthetic local development and tests. The first-admin CLI is interactive and refuses production unless `--confirm-production` is supplied and the operator also types the confirmation phrase; do not use that override for routine deployment.

From the repository root, run frontend checks with `npm run check`. From `backend`, apply the configured test database migrations, then run `python -m pytest tests -q`. The backend test suite uses the database configured for that test environment; use synthetic fixture data only. Optional dependency review commands are `npm audit` at the repository root and `python -m pip_audit -r requirements.txt` from `backend` when `pip-audit` is installed.

For the opt-in live SMTP/Mailpit authentication journey, use a **disposable development/test database**, start Mailpit and configure the backend to send SMTP to it, then run `MDIS_MAILPIT_E2E=1 python -m pytest tests/integration/test_mailpit_auth_e2e.py -q` from `backend`. The test creates synthetic accounts and emails and exercises registration, email verification, administrator approval, password reset, revocation of the existing session, and sign-in with the replacement password. See [the Stage 6 integration runbook](docs/security/stage-6-runbook.md) for PowerShell commands and the manual browser checklist.

Email recovery and invitation delivery use `EMAIL_PROVIDER`, `EMAIL_FROM`, and the selected provider's environment variables: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER` (or legacy `SMTP_USERNAME`), `SMTP_PASSWORD`, `SMTP_STARTTLS`; `RESEND_API_KEY`; or `SENDGRID_API_KEY`. Delivery timeout and retry settings are `EMAIL_SEND_TIMEOUT_SECONDS`, `EMAIL_RETRY_ATTEMPTS`, and `EMAIL_RETRY_BACKOFF_SECONDS`. The app does not expose action links in API responses. Console link delivery is for explicit local development only.

See [the security threat model](docs/security/threat-model.md) and [the operations runbook](docs/security/operations-runbook.md) for control coverage, recovery procedures, and residual risks.
