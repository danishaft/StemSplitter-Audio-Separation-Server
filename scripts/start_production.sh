#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env.production.local}"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/../venv}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  source "$ENV_FILE"
  set +a
fi

"$VENV_DIR/bin/python" -c \
  'from splitter.runtime import validate_runtime_config; validate_runtime_config()'
exec "$VENV_DIR/bin/python" -m scripts.run_api
