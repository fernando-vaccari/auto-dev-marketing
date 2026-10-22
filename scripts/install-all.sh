#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
bash scripts/install-reels.sh
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-${project_dir}/.cache/pip}"
.venv/bin/python -m pip install --disable-pip-version-check -r requirements-integrations.txt -r requirements-reels-kokoro.txt
.venv/bin/python scripts/install_voice.py
if [ "${1:-}" = '--com-obs' ] && ! command -v obs >/dev/null; then
  if [ "$(id -u)" -eq 0 ]; then
    apt-get update
    apt-get install -y --no-install-recommends obs-studio
  elif command -v sudo >/dev/null; then
    sudo apt-get update
    sudo apt-get install -y --no-install-recommends obs-studio
  else
    echo 'OBS requer instalação pelo administrador: apt install obs-studio. As demais funções locais estão instaladas.' >&2
    exit 1
  fi
fi
.venv/bin/python -m pip check
.venv/bin/python scripts/diagnose.py
