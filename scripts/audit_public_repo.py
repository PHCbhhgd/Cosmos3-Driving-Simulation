"""Audit the public source tree without reading ignored runtime data or credentials."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {
    ".git",
    "storage",
    "repos",
    "outputs",
    "artifacts",
    "release",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
}
SECRET = re.compile(
    r"(?:hf_[A-Za-z0-9]{30,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})"
)
LOCAL_PATH = re.compile(r"/(?:home|mnt)/[A-Za-z0-9][^\s\"<>]*")


def candidates(root):
    for directory, directories, names in os.walk(root):
        directories[:] = sorted(d for d in directories if d not in EXCLUDED)
        for name in sorted(names):
            yield Path(directory) / name


def audit(root=ROOT):
    errors = []
    files = list(candidates(root))
    for path in files:
        relative = path.relative_to(root)
        if path.is_symlink():
            errors.append(f"Symlink in public source: {relative}")
            continue
        if path.stat().st_size > 10 * 1024 * 1024:
            errors.append(f"File exceeds 10 MiB public-source budget: {relative}")
        if path.suffix.lower() not in {".gif", ".jpg", ".png", ".mp4"}:
            text = path.read_text(encoding="utf-8")
            if SECRET.search(text):
                errors.append(f"Credential-like content: {relative}")
            if LOCAL_PATH.search(text):
                errors.append(f"Machine-specific absolute path: {relative}")
            if path.suffix == ".md":
                for target in re.findall(r"\]\(([^)]+)\)", text):
                    if re.match(r"[a-z]+://|#|mailto:", target):
                        continue
                    destination = target.split("#", 1)[0]
                    if destination and not (path.parent / destination).exists():
                        errors.append(f"Broken local link in {relative}: {destination}")
    if (root / ".git").exists():
        tracked = subprocess.check_output(["git", "-C", str(root), "ls-files", "-z"], text=True)
        for name in tracked.split("\0"):
            if name and any(part in EXCLUDED for part in Path(name).parts):
                errors.append(f"Runtime data is tracked by Git: {name}")
    config = root / "configs/versions.json"
    if config.exists():
        versions = json.loads(config.read_text())
        patch = root / "patches/framework-low-memory.patch"
        if hashlib.sha256(patch.read_bytes()).hexdigest() != versions["patch_sha256"]:
            errors.append("Pinned patch hash mismatch")
    return {
        "status": "passed" if not errors else "failed",
        "files": len(files),
        "total_bytes": sum(p.stat().st_size for p in files if not p.is_symlink()),
        "errors": errors,
        "scope": "Public source files only; ignored local runtime is excluded.",
    }


def main():
    report = audit()
    print(json.dumps(report, indent=2))
    return int(bool(report["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
