#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="${VENV_DIR:-$SCRIPT_DIR/../venv}"
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "Python environment not found at $VENV_DIR" >&2
  exit 1
fi

if [[ -f "$SCRIPT_DIR/.env.local" ]]; then
  set -a
  source "$SCRIPT_DIR/.env.local"
  set +a
fi

if command -v npm >/dev/null 2>&1 && [[ -d "$SCRIPT_DIR/frontend/node_modules" ]]; then
  npm --prefix "$SCRIPT_DIR/frontend" run build
fi

echo "Starting Stem Separator server at http://localhost:5000 ..."
"$VENV_DIR/bin/python" audio_api.py &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT INT TERM

sleep 2
xdg-open http://localhost:5000 2>/dev/null || true

echo "Server running (PID $SERVER_PID). Press Ctrl+C to stop."
wait "$SERVER_PID"
