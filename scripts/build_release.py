"""Build path-redacted, checksum-verified sensor bundles for a GitHub Release."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import tempfile

ALLOWED = {
    ".json",
    ".csv",
    ".npz",
    ".npy",
    ".tar",
    ".mp4",
    ".ply",
    ".safetensors",
    ".html",
    ".py",
    ".jpg",
    ".png",
    ".md",
}


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def inventory(root):
    return sorted(p for p in root.rglob("*") if p.is_file() and p.name != "SHA256SUMS")


def verify(root):
    expected = {}
    for line in (root / "SHA256SUMS").read_text().splitlines():
        checksum, name = line.split("  ", 1)
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Unsafe source checksum path")
        if digest(path) != checksum:
            raise ValueError(f"Source checksum mismatch: {name}")
        expected[name] = checksum
    actual = {str(p.relative_to(root)) for p in inventory(root)}
    if actual != set(expected):
        raise ValueError("Source inventory is incomplete or has unlisted files")
    return expected


def redact(value, source_root):
    if isinstance(value, dict):
        return {k: redact(v, source_root) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, source_root) for v in value]
    if isinstance(value, str):
        return value.replace(str(source_root).rstrip("/") + "/", "").replace(
            str(source_root).rstrip("/"), "<REPRO_ROOT>"
        )
    return value


def copy_bundle(source, destination, source_root):
    verify(source)
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError("Symlinks are not distributable")
        if not path.is_file() or path.name == "SHA256SUMS":
            continue
        if path.suffix not in ALLOWED:
            raise ValueError(f"Unexpected bundle file type: {path.name}")
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".json":
            value = redact(json.loads(path.read_text()), source_root)
            target.write_text(json.dumps(value, indent=2) + "\n")
        else:
            shutil.copy2(path, target)
    (destination / "SHA256SUMS").write_text(
        "".join(
            f"{digest(path)}  {path.relative_to(destination)}\n" for path in inventory(destination)
        )
    )
    verify(destination)


def build(straight, left_shift, comparison, source_root, output):
    archive = output / "cosmos3-trajectory-sensors.tar.gz"
    if archive.exists() or archive.with_suffix(archive.suffix + ".sha256").exists():
        raise FileExistsError("Preserve existing release; choose a fresh output directory")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cosmos3-release-", dir=output) as temporary:
        staging = Path(temporary) / "cosmos3-trajectory-sensors"
        for name, source in [("straight-61", straight), ("lane-change-61", left_shift)]:
            copy_bundle(source, staging / "bundles" / name, source_root)
        shutil.copy2(comparison, staging / "trajectory-comparison.mp4")
        (staging / "README.md").write_text(
            "# Cosmos3 trajectory-conditioned RGB + LiDAR\n\n"
            "Two actual Transfer-Auto generations. Seven 832x480 videos, 61 frames/30 FPS "
            "and 20 LiDAR sweeps/10 Hz per variant.\n\n"
            "Serve a bundle: `python3 bundles/straight-61/serve_replay.py "
            "bundles/straight-61 --port 8080`; open http://127.0.0.1:8080.\n\n"
            "Verify inside each bundle with `sha256sum -c SHA256SUMS`. Metadata paths "
            "were redacted and these checksums differ from the original local bundles.\n\n"
            "Open-loop generation only. Poses are inputs; RGB/LiDAR have geometry errors. "
            "No policy/physics feedback, radar, IMU or GNSS. Not ground truth.\n"
        )
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(staging, arcname=staging.name)
    checksum = digest(archive)
    archive.with_suffix(archive.suffix + ".sha256").write_text(f"{checksum}  {archive.name}\n")
    return {
        "archive": archive.name,
        "sha256": checksum,
        "bytes": archive.stat().st_size,
        "bundle_checksums_verified": True,
        "metadata": "JSON server paths redacted; bundle checksums regenerated",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--straight", type=Path, required=True)
    parser.add_argument("--left-shift", type=Path, required=True)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--redact-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("release"))
    args = parser.parse_args()
    print(
        json.dumps(
            build(
                args.straight.resolve(),
                args.left_shift.resolve(),
                args.comparison.resolve(),
                args.redact_root.resolve(),
                args.output.resolve(),
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
