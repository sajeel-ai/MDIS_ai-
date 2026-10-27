# Safe retention purge executor (design only)

Live audit-log deletion remains disabled. The application currently enforces
dry-run for the audit stream because its ordinary database role must not bypass
the append-only audit boundary.

If audit purging is required, evaluate these options with the database and
compliance owners:

1. **Restricted database function:** a `SECURITY DEFINER` function owned by a
   dedicated role accepts a bounded cutoff, clamps it to at least six years,
   selects only rows older than that floor with `legal_hold = false`, and
   deletes only those rows. The app role receives `EXECUTE` on this function,
   never table `DELETE`.
2. **Separate immutable purge-run ledger:** record requester, approver, cutoff,
   affected count, execution id, and timestamp in a separately protected,
   append-only ledger before/after execution. Do not write the audit record into
   the stream that is being deleted.
3. **Two-person approval and bounded batches:** require a second administrator,
   capped batch size, dry-run count, and a durable operation id to make retries
   idempotent. Legal holds must be checked by the database executor itself.
4. **External archive before deletion:** require an independently encrypted,
   access-logged archive and verified retention period before the executor can
   delete eligible source rows.

Implementation should wait for a documented retention policy, legal approval,
backup/archive controls, and an isolated integration test environment. No
executor or permission change is implemented by this note.
