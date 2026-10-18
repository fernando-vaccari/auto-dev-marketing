#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
python3 -c 'import sys; assert sys.version_info >= (3, 12), "Use Python 3.12 ou superior"'
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-${project_dir}/.cache/pip}"
.venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt
.venv/bin/python -m pip check
