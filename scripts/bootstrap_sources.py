"""Fetch the exact upstream revision and apply the two-file compatibility patch."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--skip-lfs", action="store_true", help="Nano only: omit WSM renderer assets")
args = parser.parse_args()
config = json.loads((ROOT / "configs/versions.json").read_text())
source = config["source"]
repo = ROOT / "repos/cosmos-framework"


def run(*cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


if not repo.exists():
    repo.parent.mkdir(parents=True, exist_ok=True)
    run(
        "git",
        "clone",
        "--filter=blob:none",
        "--no-checkout",
        source["url"],
        str(repo),
        env=os.environ | {"GIT_LFS_SKIP_SMUDGE": "1"},
    )
    run(
        "git",
        "-C",
        str(repo),
        "checkout",
        "--detach",
        source["commit"],
        env=os.environ | {"GIT_LFS_SKIP_SMUDGE": "1"},
    )
actual = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
if actual != source["commit"]:
    raise SystemExit("Existing checkout is a different revision; preserved without reset.")
assert hashlib.sha256((repo / "uv.lock").read_bytes()).hexdigest() == source["lockfile_sha256"]
patch = ROOT / "patches/framework-low-memory.patch"
assert hashlib.sha256(patch.read_bytes()).hexdigest() == config["patch_sha256"]
base = ["git", "-C", str(repo), "apply"]
if subprocess.run(base + ["--reverse", "--check", str(patch)], capture_output=True).returncode == 0:
    print("Expected patch already applied.")
else:
    run(*base, "--check", str(patch))
    run(*base, str(patch))
if not args.skip_lfs:
    run("git", "-C", str(repo), "lfs", "install", "--local")
    run(
        "git",
        "-C",
        str(repo),
        "lfs",
        "pull",
        "--include=.agents/skills/cookbooks/cosmos3/simulation/auto/wsm/**",
    )
print(f"Ready: {source['url']}@{actual}")
