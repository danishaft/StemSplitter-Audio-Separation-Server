#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -x ".venvs/gpu-worker/bin/python" ]; then
  python3 -m venv .venvs/gpu-worker
fi

.venvs/gpu-worker/bin/python -m pip install --upgrade pip
.venvs/gpu-worker/bin/python -m pip install -r requirements/modal.txt

: "${MEGA53_MODAL_APP_NAME:=stemsplitter-mvsep-mega53}"
: "${MEGA53_MODAL_GPU:=A100-80GB}"
: "${MEGA53_MODAL_CPU:=8}"
: "${MEGA53_MODAL_MEMORY_MB:=32768}"
: "${MEGA53_MODAL_TIMEOUT:=7200}"
: "${MEGA53_MODAL_MAX_CONTAINERS:=1}"
: "${MEGA53_MODAL_SCALEDOWN_WINDOW:=300}"

export MEGA53_MODAL_APP_NAME
export MEGA53_MODAL_GPU
export MEGA53_MODAL_CPU
export MEGA53_MODAL_MEMORY_MB
export MEGA53_MODAL_TIMEOUT
export MEGA53_MODAL_MAX_CONTAINERS
export MEGA53_MODAL_SCALEDOWN_WINDOW

required_files=(
  "mvsep_mega_model_bs_roformer_53_stems_v1.ckpt"
  "mvsep_mega_model_bs_roformer_53_stems.yaml"
)
volume_listing="$(
  .venvs/gpu-worker/bin/modal volume ls stemsplitter-mvsep-mega53-models /
)"
for required_file in "${required_files[@]}"; do
  if [[ "$volume_listing" != *"$required_file"* ]]; then
    printf 'Missing Modal model file: %s\n' "$required_file" >&2
    exit 2
  fi
done

.venvs/gpu-worker/bin/modal deploy workers/mvsep_mega53_gpu_worker.py
