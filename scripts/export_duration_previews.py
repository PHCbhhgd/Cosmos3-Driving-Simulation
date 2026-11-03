"""Export only completed, fully decoded RGB duration runs with source provenance."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess

from build_release import digest


def export(suite, output):
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for run in json.loads((suite / "results.json").read_text()):
        if run["status"] != "generated_and_decoded":
            continue
        folder = suite / run["case"]
        review = json.loads((folder / "review/video_diagnostics.json").read_text())
        videos = list((folder / "raw" / run["case"]).glob("vision_*.mp4"))
        if len(videos) != 1 or not review["full_decode"]:
            raise ValueError("Require one fully decoded source RGB video")
        source = videos[0]
        if review["frames"] != run["expected_frames"] or digest(source) != review["sha256"]:
            raise ValueError("Source video disagrees with its full-decode record")
        target = output / f"transfer-duration-{run['case']}.mp4"
        if target.exists():
            raise FileExistsError(target)
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
        subprocess.run(
            ["ffmpeg", "-v", "error", "-xerror", "-i", str(target), "-f", "null", "-"],
            check=True,
        )
        probe = json.loads(
            subprocess.check_output(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-count_frames",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=nb_read_frames,width,height,r_frame_rate",
                    "-of",
                    "json",
                    str(target),
                ],
                text=True,
            )
        )["streams"][0]
        if int(probe["nb_read_frames"]) != run["expected_frames"]:
            raise ValueError("Preview has lost frames")
        if [probe["width"], probe["height"]] != review["dimensions"]:
            raise ValueError("Preview dimensions changed")
        numerator, denominator = map(int, probe["r_frame_rate"].split("/"))
        if numerator / denominator != review["fps"]:
            raise ValueError("Preview FPS changed")
        sheet = target.with_suffix(".jpg")
        shutil.copy2(folder / "review/timeline.jpg", sheet)
        records.append(
            dict(
                case=run["case"],
                file=target.name,
                bytes=target.stat().st_size,
                sha256=digest(target),
                original_sha256=review["sha256"],
                frames=review["frames"],
                fps=review["fps"],
                dimensions=review["dimensions"],
                last_frame_timestamp_s=review["last_frame_timestamp_s"],
                full_preview_decode=True,
                transform="H264 CRF23; original dimensions/FPS retained",
                timeline=sheet.name,
                timeline_sha256=digest(sheet),
            )
        )
    report = dict(
        scope="One RGB view only; no LiDAR or seven-camera duration claim", videos=records
    )
    (output / "transfer-duration-previews.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("suite", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(export(args.suite, args.output), indent=2))


if __name__ == "__main__":
    main()
