# Runbook: Secrets Management and Key Rotation (Spec 12.2, 14.3)

## 1. Secrets Directory Structure

Secrets are stored in `/home/lifeos/secrets/` on the host, mounted into containers via Docker secrets:

| Secret File | Container Mount | Description |
| --- | --- | --- |
| `lifeos_kek` | `/run/secrets/lifeos_kek` | Master Key Encryption Key (32 bytes base64) |
| `ip_hmac_key` | `/run/secrets/ip_hmac_key` | HMAC key for IP anonymisation |
| `database_url` | `/run/secrets/database_url` | Connection string for `lifeos_app` |
| `database_owner_url` | `/run/secrets/database_owner_url` | Connection string for `lifeos_owner` |
| `database_jobs_url` | `/run/secrets/database_jobs_url` | Connection string for `lifeos_jobs` |
| `database_admin_write_url` | `/run/secrets/database_admin_write_url` | Connection string for `lifeos_admin` |
| `vapid_public_key` | `/run/secrets/vapid_public_key` | Web Push VAPID public key |
| `vapid_private_key` | `/run/secrets/vapid_private_key` | Web Push VAPID private key |
| `vapid_subject` | `/run/secrets/vapid_subject` | `mailto:` address for push services |
| `tunnel_token` | `/run/secrets/tunnel_token` | Cloudflare Tunnel authentication token |

## 2. Generating New Secrets

```bash
# KEK: 32 random bytes
openssl rand -base64 32 > secrets/lifeos_kek

# IP HMAC Key: 32 random bytes
openssl rand -base64 32 > secrets/ip_hmac_key

# Ensure secure permissions
chmod 600 secrets/*
```

## 3. KEK Rotation Procedure (Spec 12.2)

1. Generate new KEK:
   ```bash
   openssl rand -base64 32 > secrets/lifeos_kek_new
   ```
2. Update keyring configuration with the new version (the crypto module supports versioned keyrings).
3. Trigger re-wrapping job to re-encrypt all user DEKs under the new KEK.
4. Verify all records decrypt cleanly.
5. Retire the old KEK version.
