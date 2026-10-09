# MDIS QA test plan (Phase 0 discovery)

Status labels used later: **PASS** means executed with evidence, **FAIL** means
executed and incorrect, **BLOCKED** means execution was prevented with a recorded
reason, and **NOT TESTED** means intentionally not run yet. No cases in this file
are claims of execution.

## Common test dimensions

For every protected workflow, test: happy path; malformed and missing input;
boundary values; duplicate/double-click submission; expired session; unauthenticated
request; each allowed role; each denied role; another-organization identifier;
dependency timeout/failure; and safe error/audit behavior. Use synthetic data only.

## Workflow cases

| Workflow | Required cases | Mode |
|---|---|---|
| Registration/verification | valid approval flow; invite-only/disabled modes; weak/mismatched password; duplicate email; invalid/expired/reused code; role=admin injection; resend cooldown; enumeration/timing | UI + API |
| Approval/rejection | admin approves/rejects; clinician/operator denied; other-org user denied; duplicate action; email provider unavailable; audit event | UI + API |
| Login/session | valid login; invalid credentials; lockout/rate limit; MFA required/invalid/reused code; refresh single-flight; expired/revoked session; logout/back button; CSRF | UI + API |
| Password reset | unknown/known account response equivalence; code expiry/reuse/attempt limit; password policy/mismatch; old session revocation; email unavailable; double submit | UI + API |
| MFA | setup, QR/otpauth handling, enable, invalid code, recovery code one-time use, disable authorization, secret/log leakage | UI + API |
| Invitations/users | invite, token expiry/reuse, role change, self-role/last-admin protection, deactivate/reactivate, session revoke, concurrent update conflict, org isolation | UI + API |
| Documents | valid upload; empty/corrupt/wrong type/oversize/path traversal/script-like name; duplicate upload; list pagination/search/status; org isolation | UI + API |
| Processing | OCR/extraction success; provider failure/timeout; empty OCR; retry; duplicate start; job status after restart; honest errors | UI + API |
| Clinical/evidence | detail/entities/evidence access; missing evidence; cross-org IDOR; XSS in source/entity text; export permissions | UI + API |
| Review | queue filters; start; approve/reject/correct; clean-item approval; denied role; duplicate decision; other-org task; audit event | UI + API |
| Timeline | list and timeline; pagination; invalid/other-org patient; empty/loading/error states | UI + API |
| FHIR | not configured; valid mocked R4 metadata; wrong version; timeout; malformed/credential URL; production localhost/public rejection; push disabled; non-synthetic block; admin/operator restriction | API + UI |
| Operations/integrations | healthy/degraded/unavailable states; admin/operator access; clinician Access restricted; safe errors; no URL/token leakage | UI + API |
| Dashboard/analytics/audit | role matrix; empty states; pagination; cross-org audit/resource access; safe timestamps and metadata | UI + API |
| Settings/inactivity | policy display; change password; logout; 30-minute warning; auto logout; no cached back navigation; keyboard/dialog behavior | UI + API |

## Responsive and accessibility matrix

At widths **320, 375, 768, 1024 and 1440px**, inspect every frontend route for
horizontal page scrolling, clipped controls, fixed sidebar/header behavior,
tables/cards, loading/empty/error states, keyboard focus, dialog Escape/focus
trap, labels, contrast, and an axe scan. Record a screenshot path and viewport for
each failure or representative pass.

## Endpoint-to-test inventory requirement

Phase 1 must generate an endpoint inventory from FastAPI routes and map every route
to an automated or manual case. Any route without a case must be listed as a
coverage gap rather than assumed covered.

