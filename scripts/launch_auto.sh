#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
: "${COSMOS3_GPUS:?Select four allocated idle GPUs, e.g. COSMOS3_GPUS=0,1,2,3}"
python3 "$PROJECT_ROOT/scripts/check_gpus.py" --gpus "$COSMOS3_GPUS"
exec bash "$PROJECT_ROOT/scripts/run_env.sh" bash "$PROJECT_ROOT/scripts/run_auto.sh" "$@"
