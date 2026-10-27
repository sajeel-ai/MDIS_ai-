# MDIS Document Storage Encryption & Key Rotation Guide

## Overview

Medical documents and PHI stored by MDIS at rest in `STORAGE_PATH` (local disk, mounted volume, or object store backing) are encrypted using **AES-256-GCM** (Galois/Counter Mode).

This guarantees both **confidentiality** and **tamper-evident integrity** (authenticated encryption with associated data — AEAD): any modification to ciphertext or the header causes immediate decryption failure.

---

## Wire and Storage Format

New writes use V2; the reader retains V1 compatibility for existing encrypted
files. V2 stores a stable, non-secret 16-character key identifier alongside
the nonce so rotation can identify the active key without trying retired keys:

```
+---------------------+-------------------+-----------------------------------------+
| V2 header           | KEY ID            | NONCE (IV)        | CIPHERTEXT + AUTH TAG |
| 11 bytes            | 16 ASCII bytes    | 12 bytes          | Variable length      |
| b"MDIS_ENC_V2"      | SHA-256 prefix    | Cryptographic RNG | AES-256-GCM + tag    |
+---------------------+-------------------+-----------------------------------------+
```

The V2 header and key id are authenticated as associated data. V1 files are
read with the historical V1 header as associated data and can be migrated
without plaintext fallback.

---

## Configuration

Two environment variables govern encryption keys:

| Environment Variable | Description | Default |
|----------------------|-------------|---------|
| `STORAGE_ENCRYPTION_KEY` | Primary active 256-bit key used for writing new documents. Formats: 32 raw bytes, 64-char hex string, or Base64-encoded string. | Required in every environment; no built-in fallback key exists. |
| `STORAGE_ENCRYPTION_PREVIOUS_KEYS` | Comma-separated list of retired 256-bit keys used only for decrypting legacy documents during key rotation. | Empty string |

### Generating a Secure 256-bit Key

Generate a cryptographically secure 256-bit key:

```bash
# Generate base64 key
openssl rand -base64 32

# Or generate 64-char hex key
openssl rand -hex 32
```

---

## Zero-Downtime Key Rotation Procedure

To rotate encryption keys without service interruption:

### Step 1: Generate New Key
Generate a new 256-bit key in your KMS or Secrets Manager (AWS Secrets Manager, GCP Secret Manager, Azure Key Vault, or HashiCorp Vault).

### Step 2: Deploy Dual-Key Configuration
Update the application configuration:
- Set `STORAGE_ENCRYPTION_KEY` to the **new** key.
- Append the **current** key to `STORAGE_ENCRYPTION_PREVIOUS_KEYS`.

Deploy this update across backend instances:
- All incoming uploads and created documents are immediately encrypted with the **new key**.
- Historical documents encrypted with the old key remain readable via transparent fallback in `decrypt_bytes`.

### Step 3: Run Re-encryption Migration Script
Re-encrypt existing documents in storage using the active key:

```bash
# 1. Preview changes (dry-run is the default)
python backend/scripts/rotate_storage_key.py --storage-dir /path/to/storage

# 2. Execute rotation after setting the new active key and old key in
#    STORAGE_ENCRYPTION_PREVIOUS_KEYS
python backend/scripts/rotate_storage_key.py --storage-dir /path/to/storage --apply

# 3. Re-run --apply: already-current files are verified and left unchanged.
python backend/scripts/rotate_storage_key.py --storage-dir /path/to/storage --apply
```

The script writes ciphertext to a same-directory temporary file, decrypt-verifies
it with the active key, checks the embedded key id, and atomically replaces the
original. Run the existing `migrate_storage_encryption.py` first when converting
pre-encryption plaintext files; rotation also encrypts plaintext files it finds.

### Step 4: Decommission Retired Key
Once migration and verification confirm that all stored files are encrypted with the active key:
- Remove the old key from `STORAGE_ENCRYPTION_PREVIOUS_KEYS`.
- Archive the retired key in your KMS according to your health system's audit and retention policy.

---

## Deployment & Operational Considerations

1. **Volume Snapshots**: Always trigger a snapshot of the storage volume before running bulk migrations.
2. **Hardware Acceleration**: AES-256-GCM utilizes CPU hardware instructions (`AES-NI` on x86_64, `ARMv8 Crypto` on ARM) ensuring negligible latency overhead (<0.1ms for a 5MB document).
3. **Tamper Detection**: Any bit modification or byte corruption results in `cryptography.exceptions.InvalidTag`. The system treats this as a security anomaly and refuses to load unverified data.
4. **Disaster Recovery**: Backups of encrypted storage volumes do not contain plaintext PHI. However, backups are only recoverable if the corresponding encryption keys in KMS are also backed up. Ensure cross-region KMS key replication.

