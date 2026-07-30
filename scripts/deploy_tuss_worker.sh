#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -x ".venvs/gpu-worker/bin/modal" ]]; then
  echo "Missing .venvs/gpu-worker/bin/modal. Create or repair the GPU worker venv first." >&2
  exit 1
fi

.venvs/gpu-worker/bin/modal deploy workers/tuss_gpu_worker.py
