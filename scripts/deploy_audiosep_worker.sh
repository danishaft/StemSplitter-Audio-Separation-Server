#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VENV_DIR="${VENV_DIR:-.venvs/gpu-worker}"
MODAL_BIN="${MODAL_BIN:-$VENV_DIR/bin/modal}"
PYTHON_BIN="${PYTHON_BIN:-$VENV_DIR/bin/python}"
MODEL_VOLUME="${AUDIOSEP_MODEL_VOLUME:-stemsplitter-audiosep-models}"

: "${AUDIOSEP_MODAL_APP_NAME:=stemsplitter-audiosep}"
: "${AUDIOSEP_MODAL_GPU:=A100-80GB}"
: "${AUDIOSEP_MODAL_CPU:=8}"
: "${AUDIOSEP_MODAL_MEMORY_MB:=32768}"
: "${AUDIOSEP_MODAL_TIMEOUT:=7200}"
: "${AUDIOSEP_MODAL_MAX_CONTAINERS:=1}"
: "${AUDIOSEP_MODAL_SCALEDOWN_WINDOW:=300}"

export AUDIOSEP_MODAL_APP_NAME
export AUDIOSEP_MODAL_GPU
export AUDIOSEP_MODAL_CPU
export AUDIOSEP_MODAL_MEMORY_MB
export AUDIOSEP_MODAL_TIMEOUT
export AUDIOSEP_MODAL_MAX_CONTAINERS
export AUDIOSEP_MODAL_SCALEDOWN_WINDOW

"$PYTHON_BIN" -m pip install --upgrade pip
"$PYTHON_BIN" -m pip install -r requirements/modal.txt

volume_listing="$("$MODAL_BIN" volume ls "$MODEL_VOLUME" /)"
grep -q "pytorch_model.bin" <<<"$volume_listing"
grep -q "roberta-base" <<<"$volume_listing"

"$MODAL_BIN" deploy workers/audiosep_gpu_worker.py
