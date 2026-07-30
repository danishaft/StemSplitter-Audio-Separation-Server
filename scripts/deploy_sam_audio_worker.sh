#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -x ".venvs/gpu-worker/bin/python" ]; then
  python3 -m venv .venvs/gpu-worker
fi

.venvs/gpu-worker/bin/python -m pip install --upgrade pip
.venvs/gpu-worker/bin/python -m pip install -r requirements/modal.txt

: "${SAM_AUDIO_HF_MODAL_SECRET:=stemsplitter-huggingface}"
: "${SAM_AUDIO_MODAL_APP_NAME:=stemsplitter-sam-audio-specialists}"
: "${SAM_AUDIO_MODAL_GPU:=A100-80GB}"
: "${SAM_AUDIO_MODAL_CPU:=8}"
: "${SAM_AUDIO_MODAL_MEMORY_MB:=32768}"
: "${SAM_AUDIO_MODAL_TIMEOUT:=7200}"
: "${SAM_AUDIO_MODAL_MAX_CONTAINERS:=1}"
: "${SAM_AUDIO_MODAL_SCALEDOWN_WINDOW:=600}"

export SAM_AUDIO_HF_MODAL_SECRET
export SAM_AUDIO_MODAL_APP_NAME
export SAM_AUDIO_MODAL_GPU
export SAM_AUDIO_MODAL_CPU
export SAM_AUDIO_MODAL_MEMORY_MB
export SAM_AUDIO_MODAL_TIMEOUT
export SAM_AUDIO_MODAL_MAX_CONTAINERS
export SAM_AUDIO_MODAL_SCALEDOWN_WINDOW

if ! .venvs/gpu-worker/bin/modal secret list --json |
  .venvs/gpu-worker/bin/python -c \
    'import json, sys; target = sys.argv[1]; raise SystemExit(not any(item.get("name") == target for item in json.load(sys.stdin)))' \
    "$SAM_AUDIO_HF_MODAL_SECRET"; then
  printf 'Missing Modal secret: %s (must contain HF_TOKEN)\n' "$SAM_AUDIO_HF_MODAL_SECRET" >&2
  exit 2
fi

.venvs/gpu-worker/bin/modal deploy workers/sam_audio_gpu_worker.py
