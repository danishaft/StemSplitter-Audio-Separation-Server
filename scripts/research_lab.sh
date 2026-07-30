#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${RESEARCH_VENV:-${PROJECT_ROOT}/.venvs/research}"
PYTHON="${PYTHON:-python3}"

if [[ ! -x "${VENV}/bin/python" ]]; then
  "${PYTHON}" -m venv "${VENV}"
fi

if [[ ! -x "${VENV}/bin/jupyter-lab" ]]; then
  "${VENV}/bin/python" -m pip install --upgrade pip
  "${VENV}/bin/python" -m pip install \
    -r "${PROJECT_ROOT}/requirements/research.txt"
  "${VENV}/bin/python" -m ipykernel install --user \
    --name stemsplitter-research \
    --display-name "StemSplitter Research"
fi

if [[ "${1:-}" == "--check" ]]; then
  "${VENV}/bin/python" -c \
    "import IPython, ipykernel, ipywidgets, jupyterlab, matplotlib, pandas, seaborn, soundfile"
  exit 0
fi

cd "${PROJECT_ROOT}"
exec "${VENV}/bin/jupyter-lab" \
  --notebook-dir="${PROJECT_ROOT}" \
  "${PROJECT_ROOT}/notebooks/specialist_training_workbench.ipynb"
