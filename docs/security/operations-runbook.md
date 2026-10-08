# MDIS Security Operations Runbook

This runbook describes the current code paths. Confirm environment-specific values and access procedures with the deployment owner before production operations.

## Local setup

1. Copy `backend/.env.example` to `backend/.env`; keep credentials private and do not commit `.env`.
2. Set `DATABASE_URL` to a PostgreSQL database dedicated to local development or tests. Use generated private `JWT_SECRET_KEY` and `AUTH_ENCRYPTION_KEY` values.
3. From `backend`, install dependencies and migrate:

   ```powershell
   .\venv\Scripts\python.exe -m pip install -r requirements.txt
   .\venv\Scripts\alembic.exe upgrade head
   ```

4. Create the first administrator interactively:

   ```powershell
   .\venv\Scripts\python.exe -m scripts.create_first_admin
   ```

   There are no default credentials. Admin and operator accounts must complete MFA setup on sign-in.
5. Start the app with the repository's configured dev command. Local HTTP uses `AUTH_COOKIE_SECURE=false`; production must use HTTPS and `AUTH_COOKIE_SECURE=true`.

## Email and external providers

- Email is disabled when `EMAIL_PROVIDER` is empty. Configure SMTP, Resend, or SendGrid and `EMAIL_FROM` to deliver reset/invitation links. Do not enable console links outside development.
- OCR and extraction provider settings are `OCR_PROVIDER`, `AZURE_DOC_INTEL_ENDPOINT`, `AZURE_DOC_INTEL_KEY`, `EXTRACTION_PROVIDER`, `OPENAI_API_KEY`, and `OPENAI_MODEL`. Review outbound-data policy before enabling external providers.
- Outbound FHIR stays disabled unless explicitly enabled for a test server and synthetic data. Verify the target server and its `/metadata` response before any test push.

## Routine validation

Run frontend checks from the repository root and backend tests from `backend`:

```powershell
npm run check
python -m pytest tests -q
```

Review `npm audit` and `python -m pip_audit -r requirements.txt` findings. Avoid putting database URLs, keys, patient data, request bodies, or action links in incident tickets or shell history.

## Incident response

### Suspected credential or session compromise

1. Deactivate the affected account through the org-scoped admin UI/API. Deactivation revokes that user's active refresh sessions.
2. Revoke remaining sessions from Admin User Management if needed.
3. Reset the user's password using the recovery flow or a verified admin-assisted procedure; password reset revokes active sessions.
4. For signing-key exposure, rotate `JWT_SECRET_KEY`, restart all API instances, and require users to sign in again. This invalidates existing JWT verification; coordinate this as a planned incident action.
5. For MFA encryption-key exposure, plan re-enrollment and rotate `AUTH_ENCRYPTION_KEY`; the current code does not provide transparent multi-key decryption rotation.
6. Preserve audit records and review the event window by request ID, actor ID, organization ID, and resource IDs. Do not copy document text or credentials into logs.

### Suspected cross-organization access

1. Disable the affected account and revoke sessions.
2. Preserve request IDs and relevant audit rows; do not export sensitive content to a separate channel.
3. Identify object IDs and tenant IDs from approved audit metadata, then assess affected records using authorized database procedures.
4. Validate the route/service query scope and add a regression test before restoring access.

### Provider or processing outage

1. Disable the affected external provider by configuration and restart the service.
2. Inspect job status and safe error codes; do not treat queued/running records as completed work.
3. Retry only through the existing retry endpoint after the underlying provider/storage issue is resolved.
4. The current worker is in-process; after a process restart, inspect queued/running jobs for stranded work. Automatic durable recovery is not implemented.

## Production startup checklist

- `APP_ENV=production` and/or `ENVIRONMENT=production`; neither may conflict with development.
- Private JWT signing and MFA encryption keys are configured and protected outside the repository.
- `AUTH_DISABLED=false`, no frontend auth-bypass build flag, `DEBUG=false`, `AUTH_COOKIE_SECURE=true`.
- Exact `CORS_ORIGINS` allowlist; no wildcard with credentials.
- OCR and extraction providers are configured to real, approved implementations; startup refuses `mock` providers outside development.
- Production password blocklist file is readable and non-empty.
- HTTPS termination, reverse-proxy trusted-header policy, database TLS/permissions, storage permissions, backup, retention, alerting, and outbound egress rules are independently reviewed.
- Admin/operator MFA enrollment verified; initial administrator creation is controlled and audited.
- `npm run check`, backend `pytest`, dependency audits, and migration status recorded for the release.

## Residual operational work

Production-grade durable job recovery, database-enforced tenant isolation, key rotation automation, alert routing, WAF/edge policy, SSO/SAML design, external penetration testing, and a tested disaster-recovery procedure remain future work. See [threat model](threat-model.md).
