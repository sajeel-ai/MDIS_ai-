# Backup and recovery

## PostgreSQL

[`scripts/backup-postgres.ps1`](../scripts/backup-postgres.ps1) creates a
`pg_dump` custom-format backup and encrypts it with `age`. It requires
`BACKUP_AGE_RECIPIENT`; the private identity must be held outside the
repository. Retention is count-based by default (14 encrypted backups).
The script refuses port 5432 and the `cognate_ai` database.

Production must use pgBackRest, WAL-G, or the managed PostgreSQL equivalent for
continuous WAL archiving and point-in-time recovery. Configure encrypted
repository storage, immutable/versioned object storage, lifecycle retention,
least-privilege credentials, and periodic restore drills. The application
backup script is not a substitute for WAL archiving.

## Secrets

The application resolves a secret from the direct environment variable first,
then from the corresponding `*_FILE` path. Secret files must be mounted with
least-privilege permissions and are never copied into the image. Supported
required names include `JWT_SECRET_KEY`, `STORAGE_ENCRYPTION_KEY`,
`AUTH_ENCRYPTION_KEY`, `DATABASE_PASSWORD`, `SMTP_PASSWORD`, and
`OPENAI_API_KEY`. A cloud secret-manager adapter is intentionally not selected
until the provider is named; provide the provider, account/project, secret
names, region, and workload identity mechanism before implementation.

Rotate JWT and auth-encryption keys during a controlled session invalidation
window; rotate storage keys with the existing storage-key rotation script;
rotate database and SMTP credentials in the provider first, then update the
mounted secret file; rotate LLM keys in the provider and update
`OPENAI_API_KEY_FILE`. Never print secret values during rotation or incident
response.

## Restore test

[`scripts/restore-test.ps1`](../scripts/restore-test.ps1) decrypts the latest
backup, restores it into only the disposable
`postgresql+asyncpg://test:test@localhost:5433/cognate_ai_test` database,
checks the Alembic version, verifies row counts and audit-log consistency, and
optionally decrypts a sample local stored document. A backup is not considered
recoverable until this script succeeds.

## Object storage

Enable versioning, default encryption, lifecycle retention, public-access
blocking, and object lock/legal hold in the selected S3-compatible bucket.
These settings, the backup target, cloud account, WAL archive destination,
restore operator, and alert destination are **BLOCKED** until configured by
the deployment owner.

## Decisions required

| Decision | Required input |
|---|---|
| RPO | Maximum acceptable data loss interval |
| RTO | Maximum acceptable restoration time |
| PostgreSQL backup target | pgBackRest/WAL-G or managed provider and bucket/region |
| Object storage target | Provider, bucket, region, versioning/object-lock policy |
| Restore owner | Named on-call team and escalation contact |
