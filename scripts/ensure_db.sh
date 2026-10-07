#!/usr/bin/env bash
# Start the local PostgreSQL 16 used by tests and migration checks, unless DATABASE_URL already
# points somewhere else (CI service container).
set -euo pipefail

if [[ -n "${DATABASE_URL:-}" ]]; then
  echo "db: using DATABASE_URL from the environment"
  exit 0
fi
docker compose -f "$(dirname "$0")/../infra/docker-compose.dev.yml" up -d --wait postgres
(cd "$(dirname "$0")/../server" && uv run python migrations/apply_roles.py)
