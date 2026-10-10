#!/usr/bin/env bash
# NFR-6 / Spec 12.4, 14.5: Verify no external origins appear in the web bundle.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST="${1:-$ROOT/web/dist}"

if [ ! -d "$DIST" ]; then
  echo "external-origins error: directory $DIST does not exist (run npm run build first)" >&2
  exit 1
fi

FAILURES=0

# Check 1: HTML files must not contain external scripts or stylesheets or iframes
if grep -EIn '(src|href)=["'"'"']https?://' "$DIST"/*.html 2>/dev/null; then
  echo "external-origins: found external resource URL in HTML" >&2
  FAILURES=$((FAILURES + 1))
fi

# Check 2: CSS files must not import external resources via @import or url(http...)
if grep -EIn '(@import\s+["'"'"']?https?://|url\(\s*["'"'"']?https?://)' "$DIST"/assets/*.css 2>/dev/null; then
  echo "external-origins: found external URL in stylesheets" >&2
  FAILURES=$((FAILURES + 1))
fi

# Check 3: Check CSP in _headers if present: must not allow external origins
if [ -f "$DIST/_headers" ]; then
  if grep -i "content-security-policy" "$DIST/_headers" | grep -Ei 'https?://[a-z0-9]'; then
    echo "external-origins: found external origin in Content-Security-Policy" >&2
    FAILURES=$((FAILURES + 1))
  fi
fi

if [ "$FAILURES" -ne 0 ]; then
  echo "external-origins: FAILED ($FAILURES violation(s) found)" >&2
  exit 1
fi

echo "external-origins: clean (0 external origins found)"
exit 0
