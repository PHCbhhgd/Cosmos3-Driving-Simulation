#!/usr/bin/env bash
# Install tools into this repository, then fetch immutable upstream sources.
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
if [[ "${1:-}" == --help ]]; then
  echo 'Usage: bash scripts/bootstrap.sh [--skip-lfs]'
  echo 'Requires Linux x86-64, glibc >= 2.35, python3 with venv, git and git-lfs.'
  exit 0
fi
python3 - <<'CHECK'
import platform
name, version = platform.libc_ver()
if name != 'glibc' or tuple(map(int, version.split('.')[:2])) < (2,35):
    raise SystemExit('Use Ubuntu >=22.04 (24.04 recommended) or an administrator-provided compatible container; host glibc is unchanged.')
CHECK
python3 -m venv storage/venvs/tools
storage/venvs/tools/bin/python -m pip install 'uv==0.11.29'
exec bash scripts/run_env.sh storage/venvs/tools/bin/python scripts/bootstrap_sources.py "$@"
