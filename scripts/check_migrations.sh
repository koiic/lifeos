#!/usr/bin/env bash
# Migration check (plan 4.5, 6.1): upgrade -> downgrade -> upgrade must run clean.
set -euo pipefail

cd "$(dirname "$0")/../server"
uv run alembic upgrade head
uv run alembic downgrade base
uv run alembic upgrade head
echo "migrations: upgrade -> downgrade -> upgrade clean"
