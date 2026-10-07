#!/usr/bin/env bash
# Migration check (plan 4.5, 6.1): upgrade -> downgrade -> upgrade must run clean.
set -euo pipefail

# Developer and CI tooling runs as a local deployment unless told otherwise (spec 14.3).
export ENV="${ENV:-local}"

cd "$(dirname "$0")/../server"
# Roles are cluster-wide and created outside migrations (T03 Decisions).
uv run python migrations/apply_roles.py
uv run alembic upgrade head
uv run alembic downgrade base
uv run alembic upgrade head
echo "migrations: upgrade -> downgrade -> upgrade clean"
