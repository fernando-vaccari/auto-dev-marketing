#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
if ! command -v "${REELS_FFMPEG:-ffmpeg}" >/dev/null || ! command -v "${REELS_FFPROBE:-ffprobe}" >/dev/null || ! command -v "${REELS_ESPEAK_NG:-espeak-ng}" >/dev/null; then
  if [ "$(id -u)" -eq 0 ]; then
    apt-get update
    apt-get install -y --no-install-recommends ffmpeg espeak-ng python3-venv
  elif command -v sudo >/dev/null; then
    sudo apt-get update
    sudo apt-get install -y --no-install-recommends ffmpeg espeak-ng python3-venv
  else
    echo 'Instale ffmpeg, espeak-ng e python3-venv com o administrador e execute novamente.' >&2
    exit 1
  fi
fi
bash scripts/install.sh
.venv/bin/python -m app.reels doctor
