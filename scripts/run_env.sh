#!/usr/bin/env bash
# Project caches only; preserve authentication, proxies and driver library paths.
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export HF_HOME="${HF_HOME:-${XDG_CACHE_HOME:-$HOME/.cache}/huggingface}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$PROJECT_ROOT/storage/cache/uv}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$PROJECT_ROOT/storage/python}"
export TORCH_HOME="${TORCH_HOME:-$PROJECT_ROOT/storage/cache/torch}"
export TRITON_CACHE_DIR="${TRITON_CACHE_DIR:-$PROJECT_ROOT/storage/cache/triton}"
export NLTK_DATA="${NLTK_DATA:-$PROJECT_ROOT/storage/cache/nltk}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-8}"
export PYTHONUNBUFFERED=1
if [[ -n "${COSMOS3_GPUS+x}" ]]; then export CUDA_VISIBLE_DEVICES="$COSMOS3_GPUS"; fi
mkdir -p "$PROJECT_ROOT/artifacts" "$PROJECT_ROOT/outputs"
export PATH="$PROJECT_ROOT/storage/bin:$PROJECT_ROOT/storage/venvs/tools/bin:$PATH"
exec "$@"
