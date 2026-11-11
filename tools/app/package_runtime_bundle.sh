#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

cd "$REPO_ROOT"
if [[ -x ".venv/bin/python" ]]; then
  .venv/bin/python tools/app/build_runtime_bundle.py --zip "$@"
elif [[ -x ".venv/Scripts/python.exe" ]]; then
  .venv/Scripts/python.exe tools/app/build_runtime_bundle.py --zip "$@"
else
  uv run python tools/app/build_runtime_bundle.py --zip "$@"
fi
