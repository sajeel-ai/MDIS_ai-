# Stage 6: Integration and local QA runbook

Use synthetic identities and a disposable development database only. Do not run these steps against a production database, SMTP provider, or real account.

## Start local services

From the repository root, first make sure the root `.env` has a private local PostgreSQL password, then start the existing Compose services:

```powershell
docker compose up -d postgres mailpit
```

Open Mailpit at `http://localhost:8025`. The host SMTP endpoint is `127.0.0.1:1025`. Start the backend with `EMAIL_PROVIDER=smtp`, `SMTP_HOST=127.0.0.1`, `SMTP_PORT=1025`, `SMTP_STARTTLS=false`, a local `EMAIL_FROM`, and `REGISTRATION_MODE=approval`. Apply migrations and start the frontend with the existing development commands. Do not use real credentials in the test.

The application process and the integration test process must both use SMTP settings that point to Mailpit. The test also needs a disposable PostgreSQL database configured by `DATABASE_URL` and the migrated default organization. The test signs its synthetic administrator through the normal JWT verification dependency, then calls the same protected approval endpoint used by the application.

## Automated real-mail journey

From `backend` in PowerShell, configure the test process before importing the app. Keep any local database password in your ignored `.env`; do not put it in command history or this document.

```powershell
$env:APP_ENV = "development"
$env:AUTH_DISABLED = "false"
$env:MDIS_MAILPIT_E2E = "1"
$env:MAILPIT_URL = "http://127.0.0.1:8025"
$env:EMAIL_PROVIDER = "smtp"
$env:EMAIL_FROM = "Cognate AI <no-reply@localhost>"
$env:PUBLIC_APP_URL = "http://localhost:8443"
$env:SMTP_HOST = "127.0.0.1"
$env:SMTP_PORT = "1025"
$env:SMTP_STARTTLS = "false"
$env:REGISTRATION_MODE = "approval"
.env\Scripts\python.exe -m pytest tests/integration/test_mailpit_auth_e2e.py -q
```

The test uses randomized `example.test` addresses and synthetic names. It reads verification codes from Mailpit's local API without printing message content, verifies the account, approves it, checks the approval message, signs in, resets the password, checks that the old session no longer reads `/auth/me`, and signs in with the new password. It is skipped in the normal suite unless `MDIS_MAILPIT_E2E=1` is explicitly set. The test does not clean persistent database records, so use a disposable database.

## Manual browser checklist

Use the running development frontend and synthetic account created by the approved registration flow.

1. Register a synthetic user. Confirm a verification code message arrives in Mailpit; enter the code in the app and confirm the account shows an awaiting-approval state.
2. Sign in as an administrator, open Admin User Management, approve the pending request, and confirm the approval email arrives in Mailpit.
3. Confirm the user can sign in after approval and can reach an authorized page.
4. Keep the user signed in in one tab. In a second tab, request a password reset, read the code from Mailpit, verify it, and choose a new synthetic password.
5. Reload the old tab and confirm it returns to sign-in. Sign in with the new password and confirm the old password is rejected.
6. Check at 320, 375, 768, 1024, and 1440 CSS pixels: no horizontal page overflow, inputs/buttons remain reachable, and pending/rejected/status messages are readable.
7. Keyboard-check form labels, focus visibility, submit-on-enter, disabled/loading buttons, and status/error announcements.
8. Verify that wrong, expired, and reused codes fail; resend cooldown and daily limit are enforced; no code appears in application logs or audit metadata.

Record each viewport and browser result when this checklist is run. Source-level tests do not substitute for the live browser checks.

## OWASP control map and residual risk

The existing [threat model](threat-model.md) maps STRIDE threats to controls and tests. The current staged authentication coverage maps to the OWASP Top 10 as follows; the mapping is a code/test inventory, not a certification claim.

| OWASP Top 10 (2021) | Relevant control | Test evidence / limitation |
|---|---|---|
| A01 Broken Access Control | Server-side role and organization checks; same-origin return-path validation | Authz and route tests exist; a complete live IDOR matrix was not run in this stage. |
| A02 Cryptographic Failures | Argon2id password hashes, hashed refresh/action/code tokens, encrypted MFA secret, secure cookie settings | Unit/security tests exist; production key and cookie deployment settings were not inspected live. |
| A03 Injection | Pydantic request validation and SQLAlchemy bound expressions | Existing backend tests; no dynamic penetration test in this stage. |
| A04 Insecure Design | Registration approval, rate limits, expiring single-use codes, session revocation | Registration/code tests and opt-in Mailpit journey; live journey requires local services. |
| A05 Security Misconfiguration | Startup guards, exact CORS allowlist, production bypass refusal | Configuration tests exist; production deployment configuration was not observed here. |
| A06 Vulnerable and Outdated Components | npm/pip dependency audit | Results are recorded in the Stage 6 report; package feeds/tool availability may limit audit freshness. |
| A07 Identification and Authentication Failures | Generic login/reset responses, lockout, MFA, rotating sessions | Existing auth/security tests and opt-in Mailpit reset flow; real Mailpit test was not run in this environment. |
| A08 Software and Data Integrity Failures | Pinned dependency lockfiles and CI checks | CI workflow is configured; no external CI run was observed. |
| A09 Security Logging and Monitoring Failures | ID/action-only audit events and secret redaction | Audit tests assert codes/secrets are absent; deployed log aggregation was not inspected. |
| A10 Server-Side Request Forgery | No user-controlled outbound URL in tested auth flows; provider destinations come from configuration | Auth tests do not constitute a general SSRF assessment; other provider/network paths need separate review. |

Additional controls: open redirects are rejected by `safeReturnPath` tests; CSRF cookies/headers are enforced in auth tests; refresh rotation and replay handling have security tests. Residual risks include no live browser/device run in this stage, no external penetration test, no verified production secret rotation, and no review of deployed mail/domain/database controls.
