#!/usr/bin/env bash
# Run in a compatible native OS or provisioned container. Keep upstream uv.lock.
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export UV_PROJECT_ENVIRONMENT="$PROJECT_ROOT/storage/venvs/auto"
export UV_HTTP_TIMEOUT="${UV_HTTP_TIMEOUT:-600}"
cd "$PROJECT_ROOT/repos/cosmos-framework"
uv sync --locked --no-dev --python 3.13 --group cu130-train --extra train --extra guardrail
UV_PROJECT_ENVIRONMENT="$PROJECT_ROOT/storage/venvs/framework-hf-cli"   uv sync --project cosmos_framework/utils/hf_cli --locked --no-default-groups --python 3.13
# Review/evaluation tools live separately, without changing the locked Auto runtime.
uv venv --python 3.12 "$PROJECT_ROOT/storage/venvs/review"
uv pip install --python "$PROJECT_ROOT/storage/venvs/review/bin/python"   -r "$PROJECT_ROOT/configs/review-requirements.txt"
