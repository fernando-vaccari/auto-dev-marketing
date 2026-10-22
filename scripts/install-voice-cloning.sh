#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
# Não toca na .venv principal, no .env ou no banco.
compatible_python="${VOICE_CLONE_PYTHON:-python3.12}"
exec "$compatible_python" scripts/install_voice_cloning.py "$@"
