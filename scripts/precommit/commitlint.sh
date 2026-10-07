#!/usr/bin/env bash
# commit-msg hook: lint the message with web/commitlint.config.js (plan 4.1).
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT/web"
exec npx --no-install commitlint --edit "$ROOT/$1"
