#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
uv venv --python 3.12 "$PROJECT_ROOT/storage/venvs/cosmos3"
uv pip install --python "$PROJECT_ROOT/storage/venvs/cosmos3/bin/python"   --torch-backend=cu130 -r "$PROJECT_ROOT/configs/nano-constraints.txt"   "$PROJECT_ROOT/repos/cosmos-framework/packages/diffusers-cpu-offloading"
