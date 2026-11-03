"""Collect existing benchmark evidence without treating pending runs as completed."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from build_release import redact

ROOT = Path(__file__).resolve().parents[1]


def collect(suite, output, source_root=ROOT):
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for folder in sorted(p for p in suite.iterdir() if p.is_dir()):
        run = folder / "run.json"
        if not run.exists():
            continue
        record = redact(json.loads(run.read_text()), source_root)
        rows.append(record)
        destination = output / folder.name
        destination.mkdir(exist_ok=True)
        (destination / "run.json").write_text(json.dumps(record, indent=2) + "\n")
        evidence = [
            folder / "gpu_preflight.json",
            folder / "browser.json",
            folder / "review/video_diagnostics.json",
            folder / "bundle/bundle_manifest.json",
            folder / "bundle/review/temporal_diagnostics.json",
            folder / "bundle/review/control_depth_agreement.json",
            folder / "bundle/review/actor_support.json",
        ]
        for path in evidence:
            if path.exists():
                target = destination / path.name
                target.write_text(
                    json.dumps(redact(json.loads(path.read_text()), source_root), indent=2) + "\n"
                )
        sums = folder / "bundle/SHA256SUMS"
        if sums.exists():
            shutil.copy2(sums, destination / "original-bundle-SHA256SUMS")
    report = dict(
        collected_at=datetime.now(timezone.utc).isoformat(),
        scope="Snapshot of files that exist. Running, missing and failed results are not "
        "visual-quality passes; original bundle hashes differ after release redaction.",
        cases=rows,
    )
    (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("suite", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(collect(args.suite, args.output), indent=2))


if __name__ == "__main__":
    main()
