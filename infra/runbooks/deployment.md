# Runbook: Deployment and Operations (Spec 14, ADR-0001, CR-006, CR-015)

## 1. Architecture Overview

- **Web Frontend**: Cloudflare Pages serving the static PWA built from `web/`.
- **API Proxy**: Cloudflare Pages Function at `web/functions/api/[[path]].ts` forwarding `/api/*` requests to the origin VPS via Cloudflare Tunnel.
- **Origin Access**: Protected by Cloudflare Access service token (`CF-Access-Client-Id` and `CF-Access-Client-Secret`).
- **Server VPS**: Runs `infra/docker-compose.yml`:
  - `cloudflared`: Connects out to Cloudflare Tunnel; ingress to `api:8000`.
  - `api`: FastAPI application; read-only root FS; no published host ports (network trust per CR-015).
  - `worker`: Procrastinate async background job worker.
  - `migrate`: Runs Alembic migrations (`alembic upgrade head`) before API and worker start.
  - `postgres`: PostgreSQL 16 on private Docker network with continuous WAL archiving.
  - `backup`: Off-site backup automation.

---

## 2. Secrets Provisioning

On the VPS, create `/home/lifeos/secrets/` with restricted permissions (`chmod 700`, files `chmod 600`):

1. **Master KEK (`lifeos_kek`)**:
   ```bash
   openssl rand -base64 32 > /home/lifeos/secrets/lifeos_kek
   ```
2. **IP HMAC Key (`ip_hmac_key`)**:
   ```bash
   openssl rand -base64 32 > /home/lifeos/secrets/ip_hmac_key
   ```
3. **Database Connection Strings**:
   - `database_url`: `postgresql://lifeos_app:<pass>@postgres:5432/lifeos`
   - `database_owner_url`: `postgresql://lifeos_owner:<pass>@postgres:5432/lifeos`
   - `database_jobs_url`: `postgresql://lifeos_jobs:<pass>@postgres:5432/lifeos`
   - `database_admin_write_url`: `postgresql://lifeos_admin:<pass>@postgres:5432/lifeos`
4. **VAPID Keys**:
   ```bash
   # Generate using pywebpush CLI or server script
   uv run python -c "from pywebpush import VAPID; v = VAPID(); ..."
   ```
5. **Cloudflare Tunnel Token**:
   - `tunnel_token`: Token from Cloudflare Zero Trust dashboard.

---

## 3. VPS Host Setup

1. **Host Requirements**:
   - Ubuntu 24.04 LTS (2 vCPU, 4 GB RAM, 40 GB SSD).
   - Docker Engine and Docker Compose v2.
   - UFW firewall: inbound SSH by key only; **no inbound HTTP/HTTPS ports open**.
2. **Start Services**:
   ```bash
   cd /home/lifeos/life-os-claude-kit/infra
   docker compose up -d --build
   ```

---

## 4. Cloudflare Pages Configuration

1. **Build Settings**:
   - Framework preset: None (Vite).
   - Build command: `npm run build`.
   - Build output directory: `dist`.
   - Root directory: `web`.
2. **Environment Variables & Secrets**:
   - `ORIGIN_URL`: `https://tunnel-origin.example.com` (tunnel public hostname).
   - `CF_ACCESS_CLIENT_ID`: Cloudflare Access Service Token Client ID.
   - `CF_ACCESS_CLIENT_SECRET`: Cloudflare Access Service Token Client Secret.

---

## 5. Verification & Health Probes

1. **Readiness Probe**:
   ```bash
   curl -s -f https://app.example.com/api/v1/readyz
   # Expect: {"status":"ok"}
   ```
2. **Liveness Probe**:
   ```bash
   curl -s -f https://app.example.com/api/v1/healthz
   # Expect: {"status":"ok"}
   ```
3. **Security Headers**:
   ```bash
   curl -I https://app.example.com/
   # Verify presence of Strict-Transport-Security, Content-Security-Policy, etc.
   ```
