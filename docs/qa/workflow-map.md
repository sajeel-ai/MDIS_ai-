# MDIS QA workflow map (Phase 0 discovery)

This is a static map of the workflows found in the repository. No services were
started and no PHI or test accounts were created during this discovery phase.

## Frontend pages and entry points

| Route | Page/workflow | Protected roles | Main API areas |
|---|---|---|---|
| `/dashboard` | Dashboard metrics and recent activity | authenticated | dashboard, health |
| `/documents` | Upload, list, filter, process, retry, inspect | authenticated; upload clinician/admin | documents, patients, processing |
| `/clinical/:documentId` | Clinical workspace, extracted entities and evidence | authenticated | document detail/entities/evidence |
| `/review` | Review queue and filters | authenticated | review queue/stats/policy |
| `/review/document/:taskId` | Dedicated three-panel review workspace | authenticated; decisions reviewer/admin | review detail/start/approve/reject/correct |
| `/patients` / `/timeline` | Patient timeline | authenticated | patients/timeline |
| `/workflows` | Workflow configuration view | authenticated | workflow UI/provider APIs where present |
| `/ai-extraction` | Extraction view | authenticated | extraction/processing APIs |
| `/ai-operations` | AI jobs and health | admin/operator | aiops |
| `/integrations` | Service and FHIR status | admin/operator for restricted checks | health, integrations/FHIR |
| `/analytics` | Analytics view | admin/operator | analytics/provider APIs |
| `/audit` | Audit and compliance events | admin/operator | audit |
| `/pipeline` | Pipeline operations | admin/operator | pipeline/provider APIs |
| `/settings` | Account, security, review policy and logout | authenticated | auth, review policy |
| `/admin/users` | Org-scoped user administration | admin | admin users, invitations, sessions |
| `/login` | Login and MFA continuation | public | auth login/me/refresh/MFA |
| `/register` | Registration when enabled | public/config gated | auth register/verification |
| `/forgot-password` | Request reset code | public | forgot-password/codes |
| `/reset-password` | Verify code and set password | public | verify-reset-code/reset-password |
| `/accept-invitation` | Accept invitation | public token flow | invitation accept |
| `/change-password` | Authenticated password change | authenticated | change-password |
| `/mfa/setup`, `/mfa/verify` | MFA enrollment and verification | authenticated/public continuation | MFA endpoints |
| `/session-expired`, `/forbidden` | Session and authorization states | public state pages | none |

## Numbered workflows

1. **Registration and verification** — A visitor opens Register, submits email/name/password, the API applies `REGISTRATION_MODE`, sends a verification code when email is configured, the visitor submits the code, and the account enters approval-pending state when approval mode is enabled. Tables: users, organizations, auth action tokens, audit events. Emails: verification and pending/approval messages.
2. **Administrator approval/rejection** — An admin opens User Management, reviews account requests, approves or rejects a user, and the API writes audit data and may send an outcome email. Tables: users, audit events, auth action tokens.
3. **Login, MFA, refresh, logout and expiry** — A user submits credentials, receives HttpOnly cookie session state, completes MFA if required, refreshes through the API when access expires, and logs out through server-side invalidation. Tables: users, refresh tokens, audit events.
4. **Forgot/reset password** — A visitor requests a code, receives an enumeration-safe response/email, verifies the code, sets a new password, and existing sessions are revoked. Tables: auth action tokens, users, refresh tokens, audit events.
5. **MFA setup/verification/disable** — An authenticated user requests an enrollment secret/QR value, enables it with a code, uses MFA during login, and can disable it only through the protected flow. Tables: users, recovery codes/session records, audit events.
6. **Invitation onboarding** — An admin creates an invitation with a role, an email is sent when configured, and the recipient accepts a single-use token. Tables: auth action tokens, users, audit events.
7. **User management** — An admin lists organization users, invites, changes roles, deactivates/reactivates accounts, views sessions, and revokes a session family. Server-side admin and organization checks are required. Tables: users, refresh tokens, audit events.
8. **Document upload** — A clinician/admin uploads a supported file and patient/document metadata. The API validates size/type and stores the document/version. Tables: patients, documents, document versions, audit events.
9. **OCR, extraction and processing** — A clinician/admin starts processing or retries a failed job; OCR and extraction providers produce synthetic structured data, with processing status and errors exposed. Tables: processing jobs, extractions, clinical entities, validations, evidence.
10. **Clinical workspace and evidence** — A user opens document detail, entities, evidence spans and source text, with organization-scoped access. Tables: documents, entities, evidence, patients.
11. **Review** — Reviewer/admin starts a task, inspects validation/evidence, approves, rejects or corrects an entity, optionally approves clean document items, and audit events record the decision. Tables: review tasks, entities, validations, audit events.
12. **Patient timeline** — An authenticated user lists patients and opens an organization-scoped timeline. Tables: patients, encounters, documents.
13. **FHIR export and test push** — An authorized user requests a FHIR bundle; admin-only test push uses the configured local/test server, is disabled by default, accepts synthetic/test documents only, and writes an audit event. Tables: documents, patients, entities, audit events.
14. **AI operations and workflows** — Admin/operator views AI health, jobs, pipeline and workflow status; provider failures must remain visible as failures. Tables: processing jobs, audit events.
15. **Dashboard and analytics** — Authenticated users view dashboard summaries; admin/operator users view restricted analytics and operational metrics. Tables: aggregate queries, audit events where applicable.
16. **Audit and compliance** — Admin/operator users list audit events with organization scoping and safe metadata. Tables: audit events.
17. **Integrations status** — Admin/operator users check API/database/FHIR status. FHIR metadata requires a FHIR 4.x CapabilityStatement; clinicians see Access restricted. No credentials or full sensitive URLs should be displayed.
18. **Settings and inactivity** — An authenticated user views policy/security settings, changes password, signs out, and is warned/logged out after inactivity. Tables: users, refresh tokens, audit events.

## Coverage map and known gaps

Existing frontend and backend tests cover portions of authentication, role matrices,
review, documents, FHIR provider construction and safety. The following require
Phase 1–4 execution before they can be called covered: full UI workflow chains,
Mailpit delivery, two-organization IDOR matrices for every resource, browser
viewport/a11y scans, dependency/secrets scans, performance/load behavior, restart
durability, migration rollback, and a real HAPI integration. This document records
coverage requirements; it is not test evidence.

