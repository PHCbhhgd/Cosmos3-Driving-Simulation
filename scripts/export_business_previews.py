"""Make compact public previews while retaining hashes of original generated sensors."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess

from build_release import digest


def export(bundle, output, case):
    if not case or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in case):
        raise ValueError("Use a simple case name")
    output.mkdir(parents=True, exist_ok=True)
    prefix = f"transfer-{case}"
    mappings = {
        bundle / "cameras/camera_front_wide_120fov.mp4": f"{prefix}-front.mp4",
        bundle / "review/sensor_mosaic.mp4": f"{prefix}-sensors.mp4",
        bundle / "review/camera_contact_sheet.jpg": f"{prefix}-cameras.jpg",
        bundle / "review/wsm_overlay_contact_sheet.jpg": f"{prefix}-controls.jpg",
        bundle / "review/lidar_control_overlay.png": f"{prefix}-lidar.png",
        bundle / "review/front-timeline/timeline.jpg": f"{prefix}-timeline.jpg",
    }
    rows = []
    for source, name in mappings.items():
        target = output / name
        if target.exists():
            raise FileExistsError(f"Preserve existing preview: {name}")
        if source.suffix == ".mp4":
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-i",
                    str(source),
                    "-an",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "fast",
                    "-crf",
                    "23",
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    str(target),
                ],
                check=True,
            )
        else:
            shutil.copy2(source, target)
        rows.append(
            dict(
                file=name,
                bytes=target.stat().st_size,
                sha256=digest(target),
                original_bundle_file=str(source.relative_to(bundle)),
                original_sha256=digest(source),
                transform="H264 CRF23 preview, original dimensions/FPS retained"
                if source.suffix == ".mp4"
                else "Exact copy of generated-output diagnostic image",
            )
        )
    report = dict(
        case=case,
        scope="Previews only; original full sensor files retained in release bundles.",
        files=rows,
    )
    (output / f"{prefix}-previews.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("bundle", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--case", required=True)
    args = p.parse_args()
    print(json.dumps(export(args.bundle, args.output, args.case), indent=2))


if __name__ == "__main__":
    main()
