# PHI read audit and fail-closed behavior

Document, file, entity, evidence, validation-flag, JSON export, and FHIR export
routes use the shared `audit_read_access` dependency. Document-list and search
routes record a collection event and per-resource events. Review queue reads
record the collection and each returned review-task id; review-task detail
records the task id. Audit metadata contains identifiers and request context,
not clinical text or search terms.

Audit persistence is fail-closed: a read endpoint must not return PHI if
`record_audit_event`, its flush, or commit fails. Errors propagate through the
request and the client receives an error instead of the requested clinical
response. This is intentional; monitoring must alert on audit-store failures.

The database integration test `test_phi_read_endpoints_persist_actor_resource_action_time_and_ip`
exercises the main read surfaces and inspects stored audit rows. A separate
route test covers a failed audit flush before document detail is read.
