#!/usr/bin/env bash
# API contract check (plan 4.4, 6.1): the committed OpenAPI document and the generated TypeScript
# types match the code. Run with --write to regenerate both after an API change.
set -euo pipefail

# Developer and CI tooling runs as a local deployment unless told otherwise (spec 14.3).
export ENV="${ENV:-local}"

ROOT=$(cd "$(dirname "$0")/.." && pwd)
SPEC=server/openapi.json
TYPES=web/src/lib/api/schema.d.ts
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

(cd "$ROOT/server" && uv run python -c '
import json, sys
from app.main import app
json.dump(app.openapi(), sys.stdout, indent=2, sort_keys=True)
print()
') >"$TMP/openapi.json"
(cd "$ROOT/web" && npx --no-install openapi-typescript "$TMP/openapi.json" --output "$TMP/schema.d.ts" >/dev/null)

if [[ "${1:-}" == "--write" ]]; then
  mkdir -p "$ROOT/$(dirname "$TYPES")"
  cp "$TMP/openapi.json" "$ROOT/$SPEC"
  cp "$TMP/schema.d.ts" "$ROOT/$TYPES"
  echo "api-contract: wrote $SPEC and $TYPES"
  exit 0
fi

status=0
diff -u "$ROOT/$SPEC" "$TMP/openapi.json" || { echo "FAIL  $SPEC is out of date; run scripts/check_openapi.sh --write"; status=1; }
diff -u "$ROOT/$TYPES" "$TMP/schema.d.ts" || { echo "FAIL  $TYPES is out of date; run scripts/check_openapi.sh --write"; status=1; }
[[ $status -eq 0 ]] && echo "api-contract: $SPEC and $TYPES match the code"
exit $status
