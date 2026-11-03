"""Archive original RGB duration outputs, actual failures, and their synthetic inputs."""

import argparse
import json
from pathlib import Path
import shutil
import tarfile
import tempfile

from build_release import digest, inventory, redact, verify


def build(suite, scene, output, source_root):
    rows = json.loads((suite / "results.json").read_text())
    expected = {"front-rgb-121", "front-rgb-241", "front-rgb-397", "front-rgb-793"}
    if {row["case"] for row in rows} != expected or len(rows) != len(expected):
        raise ValueError("Require a terminal result for each requested duration")
    if any(row["status"] not in {"generated_and_decoded", "failed"} for row in rows):
        raise ValueError("Do not archive incomplete or unvalidated duration outputs")
    output.mkdir(parents=True, exist_ok=True)
    archive = output / "cosmos3-rgb-duration.tar.gz"
    if archive.exists():
        raise FileExistsError(archive)

    def copy(source, target):
        if source.is_symlink():
            raise ValueError("Do not distribute symlinks")
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix == ".json":
            target.write_text(
                json.dumps(redact(json.loads(source.read_text()), source_root), indent=2) + "\n"
            )
        else:
            shutil.copy2(source, target)

    with tempfile.TemporaryDirectory(prefix="duration-release-", dir=output) as temporary:
        staging = Path(temporary) / "cosmos3-rgb-duration"
        generated = []
        for row in rows:
            folder = suite / row["case"]
            copy(folder / "run.json", staging / "runs" / row["case"] / "run.json")
            if row["status"] == "failed":
                continue
            report = json.loads((folder / "review/video_diagnostics.json").read_text())
            videos = list((folder / "raw" / row["case"]).glob("vision_*.mp4"))
            if len(videos) != 1 or not report["full_decode"]:
                raise ValueError("Require one fully decoded RGB output")
            if report["frames"] != row["expected_frames"] or digest(videos[0]) != report["sha256"]:
                raise ValueError("Generated RGB disagrees with its diagnostic record")
            generated.append(row["case"])
            for path in sorted(folder.rglob("*")):
                if not path.is_file() or path.suffix not in {".mp4", ".jpg", ".json"}:
                    continue
                copy(path, staging / "runs" / row["case"] / path.relative_to(folder))
        copy(suite / "results.json", staging / "results.json")
        for path in sorted(scene.rglob("*")):
            if path.is_file() and path.suffix in {".json", ".csv", ".npz", ".tar", ".mp4"}:
                copy(path, staging / "scenario_inputs" / path.relative_to(scene))
        (staging / "README.md").write_text(
            "# Cosmos3 Transfer-Auto RGB duration tests\n\n"
            "Original generated videos, full-decode diagnostics and synthetic controls. "
            "The results.json statuses retain actual failures; a requested duration is "
            "not proof of a generated output. One front RGB view only, no LiDAR.\n\n"
            "Requested outputs: 121/241/397/793 frames at 30 FPS; last timestamps "
            "4/8/13.2/26.4 seconds. The 793-frame request uses two 397-frame chunks "
            "and one generated feedback frame; no frame duplication or retiming.\n\n"
            "Ego/lead travel at 6 m/s with a 24 m road-distance lead. Road controls "
            "cover a 90-degree left turn followed by tangent motion. Poses are inputs, "
            "not estimated or physical truth. See the public report for visual defects.\n\n"
            "Verify: `sha256sum -c SHA256SUMS`. Paths were redacted in JSON. "
            "Original MP4 bytes and diagnostic video SHA256 values are preserved.\n"
        )
        (staging / "SHA256SUMS").write_text(
            "".join(f"{digest(p)}  {p.relative_to(staging)}\n" for p in inventory(staging))
        )
        verify(staging)
        with tarfile.open(archive, "w:gz") as handle:
            handle.add(staging, arcname=staging.name)
    checksum = digest(archive)
    archive.with_suffix(archive.suffix + ".sha256").write_text(f"{checksum}  {archive.name}\n")
    report = dict(
        archive=archive.name,
        bytes=archive.stat().st_size,
        sha256=checksum,
        generated_cases=generated,
        terminal_cases=len(rows),
        checksums_verified=True,
    )
    (output / "duration-release-asset.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("suite", type=Path)
    p.add_argument("--scene", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--source-root", type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(build(args.suite, args.scene, args.output, args.source_root), indent=2))


if __name__ == "__main__":
    main()
