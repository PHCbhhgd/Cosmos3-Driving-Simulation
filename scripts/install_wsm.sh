#!/usr/bin/env bash
# Reuse the locked Auto runtime in a separate WSM environment.
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
uv venv --python storage/venvs/auto/bin/python --system-site-packages storage/venvs/wsm
storage/venvs/wsm/bin/python - <<'INSTALL'
from pathlib import Path
import importlib.metadata as md
import subprocess
import sysconfig
root = Path.cwd()
site = root / 'storage/venvs/auto/lib/python3.13/site-packages'
purelib = Path(sysconfig.get_paths()['purelib'])
(purelib / 'framework-runtime.pth').write_text(str(site)+'\n')
exclude = root / 'artifacts/wsm_reused_packages.txt'
exclude.write_text('\n'.join(d.metadata['Name'] for d in md.distributions(path=[str(site)]))+'\n')
subprocess.run([str(root/'storage/venvs/tools/bin/uv'),'pip','install','--python',str(root/'storage/venvs/wsm/bin/python'),
    '--excludes',str(exclude),str(root/'repos/cosmos-framework/.agents/skills/cookbooks/cosmos3/simulation/auto/wsm')],check=True)
INSTALL
