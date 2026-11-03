"""Archive completed benchmark sensor bundles with verified, redacted metadata."""

import argparse
import json
from pathlib import Path
import shutil
import tarfile
import tempfile

from build_release import copy_bundle, digest, inventory, verify


def build(suite, output, source_root):
    rows = json.loads((suite / "results.json").read_text())
    if len(rows) != 7 or any(row["status"] != "generated_and_packaged" for row in rows):
        raise ValueError(
            "Require seven completed sensor bundles; preserve failed results separately"
        )
    if any(
        row.get(key) != 0
        for row in rows
        for key in [
            "package_exit_code",
            "review_exit_code",
            "geometry_diagnostics_exit_code",
            "browser_exit_code",
        ]
    ):
        raise ValueError("Required bundle validation did not pass")
    output.mkdir(parents=True, exist_ok=True)
    archive = output / "cosmos3-business-sensors.tar.gz"
    if archive.exists():
        raise FileExistsError(archive)
    with tempfile.TemporaryDirectory(prefix="robustness-release-", dir=output) as temporary:
        staging = Path(temporary) / "cosmos3-business-sensors"
        for row in rows:
            source = suite / row["case"] / "bundle"
            target = staging / "bundles" / row["case"]
            copy_bundle(source, target, source_root)
            # Include the exact synthetic actor definitions used for diagnostics.
            scene = Path(__file__).resolve().parents[1] / "storage/scenarios" / row["case"]
            shutil.copy2(scene / "actors.json", target / "input_actors.json")
            (target / "SHA256SUMS").write_text(
                "".join(f"{digest(p)}  {p.relative_to(target)}\n" for p in inventory(target))
            )
            verify(target)
        (staging / "README.md").write_text(
            "# Cosmos3 business scenario sensors\n\n"
            "Seven actual Transfer-Auto generations, seven RGB views and joint LiDAR per case. "
            "61 RGB frames / 30 FPS, 20 scans / 10 Hz. Synthetic inputs, not real-world truth.\n\n"
            "Cases: clear/rain/snow left turns, occluded pedestrian, prescribed adjacent vehicle "
            "contact, wireframe tunnel entry, conflicting right-turn text with left-turn controls.\n\n"
            "Replay: `python3 bundles/clear_turn/serve_replay.py bundles/clear_turn --port 8080`; "
            "open http://127.0.0.1:8080. Verify inside each bundle: `sha256sum -c SHA256SUMS`.\n\n"
            "Input poses and actor boxes are prescribed. No policy/physics feedback. Weather "
            "captions do not provide calibrated precipitation sensor physics. LiDAR output "
            "range is restricted to 5–100 m. Contact has no deformation dynamics; tunnel "
            "controls contain no dense wall/roof mesh. See the public robustness report "
            "for observed defects. File validation does not establish simulation accuracy.\n"
        )
        with tarfile.open(archive, "w:gz") as handle:
            handle.add(staging, arcname=staging.name)
    checksum = digest(archive)
    archive.with_suffix(archive.suffix + ".sha256").write_text(f"{checksum}  {archive.name}\n")
    report = dict(
        archive=archive.name,
        sha256=checksum,
        bytes=archive.stat().st_size,
        cases=[r["case"] for r in rows],
        bundle_checksums_verified=True,
    )
    (output / "release-asset.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("suite", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--source-root", type=Path, required=True)
    args = p.parse_args()
    print(
        json.dumps(
            build(args.suite.resolve(), args.output.resolve(), args.source_root.resolve()), indent=2
        )
    )


if __name__ == "__main__":
    main()
