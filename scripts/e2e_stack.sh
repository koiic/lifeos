#!/usr/bin/env bash
# The API side of the e2e stack (plan 6.1 `make verify-e2e`; started by web/playwright.config.ts):
# the local PostgreSQL, a fresh `lifeos_e2e` database (fake data only), then the API on
# 127.0.0.1:8001 with ENV=local. The web side is `vite preview`, forwarding /api here.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE_DSN="${DATABASE_URL:-postgresql://lifeos:lifeos@127.0.0.1:54320/lifeos}"
E2E_DSN="${E2E_DATABASE_URL:-${BASE_DSN%/*}/lifeos_e2e}"

"$ROOT/scripts/ensure_db.sh"
cd "$ROOT/server"
uv run python -m tests.e2e.prepare "$BASE_DSN" "$E2E_DSN"

exec env ENV=local APP_ORIGIN="${APP_ORIGIN:-http://localhost:4174}" DATABASE_URL="$E2E_DSN" \
  uv run uvicorn app.main:app --host 127.0.0.1 --port "${API_PORT:-8001}" --no-access-log
