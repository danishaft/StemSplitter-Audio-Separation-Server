#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -x ".venvs/gpu-worker/bin/python" ]; then
  python3 -m venv .venvs/gpu-worker
fi

.venvs/gpu-worker/bin/python -m pip install --upgrade pip
.venvs/gpu-worker/bin/python -m pip install -r requirements/modal.txt

: "${BANDIT_MODAL_GPU:=T4}"
: "${BANDIT_KEEP_WARM:=0}"
: "${BANDIT_MODAL_TIMEOUT:=1800}"

export BANDIT_MODAL_GPU
export BANDIT_KEEP_WARM
export BANDIT_MODAL_TIMEOUT

.venvs/gpu-worker/bin/modal deploy workers/bandit_gpu_worker.py
