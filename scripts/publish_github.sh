#!/usr/bin/env bash
# Explicit publication entry point; run only with the publisher's account/identity.
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
repo="${1:?Usage: publish_github.sh owner/repository}"
[[ "$repo" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]
export PATH="$PROJECT_ROOT/storage/bin:$PATH"
command -v gh >/dev/null || { echo 'Install GitHub CLI gh in your user tools directory first.' >&2; exit 2; }
gh auth status --hostname github.com >/dev/null
if [[ ! -d .git ]]; then
  git init
  git symbolic-ref HEAD refs/heads/main
fi
[[ -n "$(git config user.name || true)" && -n "$(git config user.email || true)" ]] || {
  echo 'Configure repository-local user.name and user.email for the initial commit.' >&2; exit 2;
}
if git remote get-url origin >/dev/null 2>&1; then
  echo 'Existing origin preserved. Review it and push separately.' >&2; exit 2
fi
if gh repo view "$repo" --json name >/dev/null 2>&1; then
  echo 'Target repository already exists. Choose a new name or review it separately.' >&2; exit 2
fi
python3 -m unittest discover -s tests -v
python3 scripts/audit_public_repo.py
git add .
python3 scripts/audit_public_repo.py
if ! git diff --cached --quiet; then
  git commit -m 'Add Cosmos3 trajectory-conditioned RGB and LiDAR reproduction'
fi
gh repo create "$repo" --public --source . --remote origin --push \
  --description 'Cosmos3 driving model reproduction: trajectory-conditioned seven-camera RGB, LiDAR and synchronized replay'
