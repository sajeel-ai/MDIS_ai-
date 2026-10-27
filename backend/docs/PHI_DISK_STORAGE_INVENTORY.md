# PHI disk-write inventory

This is a source-code inventory, not a claim that filesystem, volume, or backup
encryption is enabled.

| Write path | Content / current control | Remaining requirement |
|---|---|---|
| `LocalStorageProvider.save_file` and `save_file_from_path` | Durable source files are AES-GCM encrypted before write. V2 files include a non-secret key id. | Configure protected keys; enable encrypted volumes and backups operationally. |
| Document upload staging in `routers/documents.py` | Plaintext is staged under `STORAGE_PATH` for type/page validation and then removed in `finally`. | A process kill or machine failure can leave staging data. Restrict directory ACLs and use startup stale-upload cleanup/monitoring; hard-disk secure erasure cannot be guaranteed by app code. |
| Image OCR input in `providers/ocr/local.py` | Plaintext temporary image file passed to Tesseract; removed in `finally`. | A process termination can leave it in the OS temp directory. Use an encrypted, access-restricted temp volume and cleanup monitoring. |
| PDF OCR input, rendered page images, and `pdftoppm` outputs | Plaintext inside `TemporaryDirectory`; normal exit cleans the directory. | Abrupt termination can leave temp contents. Use encrypted temp storage and stale-directory cleanup. |
| Thumbnails | No thumbnail write path found in the backend source search. | Re-inventory if a thumbnail service is added. |
| JSON/FHIR exports | Exporters return response content; no persistent export-file write was found in the searched routes/services. | Verify any reverse proxy, object-store, or download-cache configuration separately. |
| Logs | Reviewed application log statements use identifiers, host/status, or exception types; no explicit clinical text logging found in the searched backend paths. | Configure log sinks, retention, ACLs, and PHI redaction at the infrastructure layer; audit third-party middleware logs. |
| Tests, validator, and key-rotation staging | Synthetic fixtures or temporary outputs; rotation uses same-directory temporary ciphertext and atomic replacement. | Keep test storage isolated and clean temp artifacts after interrupted runs. |

Application encryption cannot replace encrypted database storage, encrypted
disks/volumes, encrypted snapshots/backups, KMS access controls, or backup
restore testing. Those are infrastructure requirements.
