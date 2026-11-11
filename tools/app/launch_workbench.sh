#!/usr/bin/env bash
set -euo pipefail

HOST="127.0.0.1"
PORT="3000"
MIN_PORT=3000
MAX_PORT=3010

if [[ $# -ge 1 ]]; then
  PORT="$1"
fi

if [[ $# -ge 2 ]]; then
  HOST="$2"
fi

if ! [[ "$PORT" =~ ^[0-9]+$ ]]; then
  echo "Port must be an integer. Received: $PORT" >&2
  exit 1
fi

if (( PORT < MIN_PORT || PORT > MAX_PORT )); then
  echo "Port must be within ${MIN_PORT}-${MAX_PORT}. Received: ${PORT}" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "$REPO_ROOT"

port_available() {
  python - "$1" <<'PY'
import socket
import sys

port = int(sys.argv[1])
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.bind(("127.0.0.1", port))
except OSError:
    print("0")
else:
    print("1")
finally:
    s.close()
PY
}

SELECTED_PORT=""
for ((p=PORT; p<=MAX_PORT; p++)); do
  if [[ "$(port_available "$p")" == "1" ]]; then
    SELECTED_PORT="$p"
    break
  fi
done

if [[ -z "$SELECTED_PORT" ]]; then
  for ((p=MIN_PORT; p<PORT; p++)); do
    if [[ "$(port_available "$p")" == "1" ]]; then
      SELECTED_PORT="$p"
      break
    fi
  done
fi

if [[ -z "$SELECTED_PORT" ]]; then
  echo "No free port found in allowed range ${MIN_PORT}-${MAX_PORT}. Stop another process in that range and retry." >&2
  exit 1
fi

if [[ "$SELECTED_PORT" != "$PORT" ]]; then
  echo "Requested port $PORT is busy. Using first available port in range: $SELECTED_PORT"
fi

if [[ ! -x ".venv/bin/python" && ! -x ".venv/Scripts/python.exe" ]]; then
  echo ".venv not found. Creating and syncing with uv..."
  uv sync
fi

echo "Launching LGR Sim Workbench on http://${HOST}:${SELECTED_PORT}"
uv run python src/app/run_local_app.py --host "$HOST" --port "$SELECTED_PORT"
