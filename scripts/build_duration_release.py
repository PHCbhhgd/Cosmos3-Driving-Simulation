"""Archive original RGB duration outputs, actual failures, and their synthetic inputs."""

import argparse
import json
from pathlib import Path
import shutil
import tarfile
import tempfile

from build_release import digest, inventory, redact, verify


def build(suite, scene, output, source_root, cases=None, archive_name="cosmos3-rgb-duration"):
    rows = json.loads((suite / "results.json").read_text())
    expected = set(cases or ["front-rgb-121", "front-rgb-241", "front-rgb-397", "front-rgb-793"])
    if {row["case"] for row in rows} != expected or len(rows) != len(expected):
        raise ValueError("Require a terminal result for each requested duration")
    if any(row["status"] not in {"generated_and_decoded", "failed"} for row in rows):
        raise ValueError("Do not archive incomplete or unvalidated duration outputs")
    output.mkdir(parents=True, exist_ok=True)
    if Path(archive_name).name != archive_name:
        raise ValueError("Archive name must be a filename stem")
    archive = output / f"{archive_name}.tar.gz"
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
        staging = Path(temporary) / archive_name
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
        manifest = json.loads((scene / "scene_manifest.json").read_text())
        requests = ", ".join(f"{r['expected_frames']} frames ({r['status']})" for r in rows)
        (staging / "README.md").write_text(
            "# Cosmos3 Transfer-Auto RGB duration tests\n\n"
            "Original generated videos, full-decode diagnostics and synthetic controls. "
            "The results.json statuses retain actual failures; a requested duration is "
            "not proof of a generated output. One front RGB view only, no LiDAR.\n\n"
            f"Requested outputs at 30 FPS: {requests}. "
            "A 793-frame request uses two 397-frame chunks "
            "and one generated feedback frame; no frame duplication or retiming.\n\n"
            f"Scenario: {manifest['benchmark_case']}. Poses and map geometry are synthetic "
            "inputs, not estimated or physical truth. See scenario_inputs/scene_manifest.json "
            "and the public report for input definitions and visual defects.\n\n"
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
    (output / f"{archive_name}-asset.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("suite", type=Path)
    p.add_argument("--scene", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--source-root", type=Path, required=True)
    p.add_argument(
        "--cases", nargs="+", help="Expected terminal case IDs; defaults to four durations"
    )
    p.add_argument("--archive-name", default="cosmos3-rgb-duration")
    args = p.parse_args()
    print(
        json.dumps(
            build(
                args.suite, args.scene, args.output, args.source_root, args.cases, args.archive_name
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
