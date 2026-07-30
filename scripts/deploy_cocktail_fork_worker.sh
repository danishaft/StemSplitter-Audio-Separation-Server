#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -x ".venvs/gpu-worker/bin/python" ]; then
  python3 -m venv .venvs/gpu-worker
fi

.venvs/gpu-worker/bin/python -m pip install --upgrade pip
.venvs/gpu-worker/bin/python -m pip install -r requirements/modal.txt

: "${COCKTAIL_FORK_MODAL_GPU:=T4}"
: "${COCKTAIL_FORK_KEEP_WARM:=0}"
: "${COCKTAIL_FORK_MODAL_TIMEOUT:=1800}"

export COCKTAIL_FORK_MODAL_GPU
export COCKTAIL_FORK_KEEP_WARM
export COCKTAIL_FORK_MODAL_TIMEOUT

.venvs/gpu-worker/bin/modal deploy workers/cocktail_fork_gpu_worker.py
