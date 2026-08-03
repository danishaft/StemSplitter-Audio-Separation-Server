#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -x ".venvs/gpu-worker/bin/python" ]; then
  python3 -m venv .venvs/gpu-worker
fi

.venvs/gpu-worker/bin/python -m pip install --upgrade pip
.venvs/gpu-worker/bin/python -m pip install -r requirements/modal.txt

: "${MODAL_GPU:=T4}"
: "${MODAL_APP_NAME:=stemsplitter-audio-separator-gpu}"
: "${GPU_WORKER_EXECUTION_MODE:=parallel}"
: "${MODAL_VOCAL_GPU:=L4}"
: "${MODAL_BROAD_GPU:=L4}"
: "${MODAL_DRUM_GPU:=L4}"
: "${GPU_WORKER_BRANCH_CPU:=4}"
: "${GPU_WORKER_BRANCH_KEEP_WARM:=0}"
: "${GPU_WORKER_OBJECT_PUBLISH_WORKERS:=4}"
: "${GPU_WORKER_ENABLE_PROFILING:=0}"
: "${GPU_WORKER_KEEP_WARM:=0}"
: "${GPU_WORKER_MAX_CONTAINERS:=1}"
: "${GPU_WORKER_SCALEDOWN_WINDOW:=600}"
: "${GPU_WORKER_MODAL_TIMEOUT:=3600}"

export MODAL_GPU
export MODAL_APP_NAME
export GPU_WORKER_EXECUTION_MODE
export MODAL_VOCAL_GPU
export MODAL_BROAD_GPU
export MODAL_DRUM_GPU
export GPU_WORKER_BRANCH_CPU
export GPU_WORKER_BRANCH_KEEP_WARM
export GPU_WORKER_OBJECT_PUBLISH_WORKERS
export GPU_WORKER_ENABLE_PROFILING
export GPU_WORKER_KEEP_WARM
export GPU_WORKER_MAX_CONTAINERS
export GPU_WORKER_SCALEDOWN_WINDOW
export GPU_WORKER_MODAL_TIMEOUT

.venvs/gpu-worker/bin/modal deploy workers/audio_separator_gpu_worker.py
