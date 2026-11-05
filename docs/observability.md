# Observability

Telemetry is designed to contain operational identifiers only. Structured logs
include the event name, level, timestamp, request ID, user ID, and organization
ID. Free-form log messages and exception text are never serialized.

`GET /api/v1/live` is a liveness probe and does not contact dependencies.
`GET /api/v1/ready` checks PostgreSQL, the processing-job table, and local
storage availability. It returns `503` until all checks pass.
`GET /api/v1/metrics` returns Prometheus text and is restricted to loopback or
private-network clients. Do not publish this route through a public ingress.

Metrics include request totals, request errors and duration, queue depth,
oldest queue age, failed/dead-letter jobs, per-stage duration, OCR/provider
errors, extraction fallbacks, review backlog, audit-write failures, storage
errors, database pool usage, database errors, and backup age. Metric labels are
restricted to route templates and
small operational enums; request bodies, query strings, filenames, note text,
names, and medical record numbers are never labels.

The alert rules are in [`deploy/alerts.yml`](../deploy/alerts.yml). Validate
them with `promtool check rules deploy/alerts.yml` in an environment that has
Prometheus tooling installed.
