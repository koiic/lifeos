#!/usr/bin/env bash
# Run a web tool from web/ on the files pre-commit passes (strips their web/ prefix).
set -euo pipefail

cd "$(dirname "$0")/../../web"
args=()
for arg in "$@"; do
  args+=("${arg#web/}")
done
exec npx --no-install "${args[@]}"
