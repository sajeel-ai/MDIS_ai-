# Stage 6: Integration and test report

**Date:** 2026-10-07  
**Scope:** Authentication UI states, email-code delivery, backend auth journey with SMTP/Mailpit, and verification evidence.  
**Data:** Synthetic `example.test` identities only. The Mailpit journey used a separately created database named `cognate_stage6_auth_e2e`, then dropped it after the run.

## Implemented

- Fixed verification email delivery. `send_verification_code` already supplied a code to `send_templated_email`, but that function did not accept the argument. The delivery wrapper swallowed the resulting error, so verification requests looked successful without sending mail. The provider now passes the code into the escaped email template, with a unit test for both text and HTML message output.
- Added an opt-in real SMTP/Mailpit integration journey covering registration, email verification, pending approval, admin approval and email, user login, password reset, old-session rejection, and login with the new password. It uses the application’s actual FastAPI handlers, database, and SMTP provider. It refuses to run unless the configured database name includes `test` or `e2e`.
- Login now presents clear pending-email, pending-approval, and rejected account states based on the backend response. The rejection reason is shown when supplied. New UI tests cover all three states.
- Corrected the README to describe the actual `REGISTRATION_MODE` setting rather than `SELF_REGISTRATION_ENABLED`.
- Added the [Stage 6 local integration runbook](stage-6-runbook.md), including Mailpit setup, manual browser QA steps, residual risks, and an OWASP Top 10 control/test map.
- Raised Vitest’s per-test timeout to 15 seconds. The authentication form tests intermittently exceeded the default 5-second limit on this machine; after the change, the isolated frontend check passed.

### Learning notes

- A **unit test** checks one small piece in isolation. The new provider test ensures a verification code makes it into the email body.
- An **integration test** connects real application parts. The Mailpit test runs the real API, database, and SMTP delivery, while Mailpit captures the test email locally.
- **Session revocation** means a password reset invalidates the browser’s existing session, so a stale tab must sign in again.

## Commands and results

| Command | Result |
|---|---|
| `npm run check` | Passed: TypeScript check, formatting check, 127 tests across 8 files, and production build. Run outside the restricted sandbox because Vite/Vitest hit Windows `spawn EPERM` in the sandbox. |
| `$env:DEBUG='false'; .\venv\Scripts\python.exe -m pytest tests -q --basetemp .pytest-stage6-final` (from `backend`) | **191 passed, 1 skipped** in 103.10s. The skipped test is the opt-in Mailpit test when the flag is absent. |
| `.\venv\Scripts\python.exe -m pytest tests/integration/test_mailpit_auth_e2e.py -q --basetemp .pytest-stage6-mailpit-final2` (from `backend`, with `MDIS_MAILPIT_E2E=1`, SMTP-to-Mailpit, and the isolated database configured) | **1 passed** in 26.21s. The separately created database was dropped afterward. |
| `npm audit --json` | Exit 0; 0 reported vulnerabilities across the installed dependency graph. |
| `python -m pip_audit -r requirements.txt` | Not run: `pip-audit` is not installed in the backend virtual environment. |
| `gitleaks detect --no-git --redact --source .` | Not run: `gitleaks` is not installed. A limited high-confidence source/test/docs scan with `rg` found no private-key, AWS-key, API-key-prefix, or JWT-shaped matches. This is not a full secrets audit. |
| `npx playwright --version` | Could not run: Playwright is not installed/cached and npm could not reach the registry in this environment. The in-app browser runtime also had no available browser. |

Vite emitted non-fatal config-loader warnings for `__dirname` and a JSON import without import attributes. The production build still completed.

## OWASP mapping and residual risks

The OWASP Top 10 (2021) A01–A10 table, plus open redirect, CSRF, session fixation, and test evidence, is in the [Stage 6 runbook](stage-6-runbook.md#owasp-control-map-and-residual-risk). The mapping describes code and test coverage; it is not a security certification.

Not completed in this stage:

- Playwright/Cypress browser automation and visual snapshots. No browser runtime was available and the dependency could not be installed offline. The Mailpit API journey passed, but it does not prove frontend browser behavior.
- Manual viewport, keyboard, and screen-reader QA at 320, 375, 768, 1024, and 1440 pixels. Follow the checklist in the runbook when a browser is available.
- `pip-audit` and a full Gitleaks scan, because those tools are absent. The `rg` scan was limited to high-confidence token patterns.
- External penetration testing, production deployment review, and independent CI status.

## Files changed

- `README.md`
- `backend/app/services/email_provider.py`
- `backend/tests/integration/test_mailpit_auth_e2e.py`
- `backend/tests/unit/test_email_delivery.py`
- `docs/security/stage-6-report.md`
- `docs/security/stage-6-runbook.md`
- `src/pages/Login.tsx`
- `src/services/api.ts`
- `src/test/authCore.test.tsx`
- `vite.config.ts`
