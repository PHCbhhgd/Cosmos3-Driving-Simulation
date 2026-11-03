"""Extract compact README scene images from actual validated local videos."""

import argparse
import json
from pathlib import Path

import cv2
from PIL import Image, ImageDraw

from build_release import digest

FRAMES = {
    "clear_turn": [0, 30, 60],
    "rain_turn": [0, 30, 60],
    "snow_turn": [0, 30, 60],
    "occluded_pedestrian": [0, 33, 48],
    "adjacent_collision": [0, 33, 60],
    "tunnel_entry": [0, 15, 60],
    "contradictory_turn": [0, 30, 60],
}


def extract(video, indices):
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise ValueError(f"Cannot read {video.name}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    images = []
    try:
        for index in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = cap.read()
            if not ok:
                raise ValueError(f"Cannot read frame {index}")
            images.append(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
    finally:
        cap.release()
    return images, fps


def export(suite, output):
    output.mkdir(parents=True, exist_ok=False)
    records = []
    for case, indices in FRAMES.items():
        folder = suite / case
        run = json.loads((folder / "run.json").read_text())
        if run["status"] != "generated_and_packaged":
            raise ValueError(f"Case not completed: {case}")
        bundle = folder / "bundle"
        source = bundle / "cameras/camera_front_wide_120fov.mp4"
        expected = dict(
            reversed(line.split("  ", 1))
            for line in (bundle / "SHA256SUMS").read_text().splitlines()
        )
        source_hash = digest(source)
        if source_hash != expected[str(source.relative_to(bundle))]:
            raise ValueError(f"Original source hash mismatch: {case}")
        frames, fps = extract(source, indices)
        sheet = Image.new("RGB", (416 * len(frames), 267), (15, 22, 30))
        for column, (frame, index) in enumerate(zip(frames, indices)):
            sheet.paste(frame.resize((416, 240)), (416 * column, 27))
            ImageDraw.Draw(sheet).text(
                (416 * column + 8, 7), f"{case} | Transfer RGB | {index / fps:.3f}s", fill="white"
            )
        target = output / f"{case}.jpg"
        sheet.save(target, quality=88)
        records.append(
            dict(
                case=case,
                file=target.name,
                sha256=digest(target),
                source_bundle_file=str(source.relative_to(bundle)),
                source_sha256=source_hash,
                frame_ids=indices,
                fps=fps,
            )
        )
    source = suite / "clear_turn/bundle/review/sensor_mosaic.mp4"
    frames, fps = extract(source, [30])
    cover = frames[0]
    cover.thumbnail((1248, 900))
    target = output / "sensors-overview.jpg"
    cover.save(target, quality=88)
    records.append(
        dict(
            case="clear_turn",
            file=target.name,
            sha256=digest(target),
            source_bundle_file="review/sensor_mosaic.mp4",
            source_sha256=digest(source),
            frame_ids=[30],
            fps=fps,
        )
    )
    report = dict(
        scope="Actual video frames; resized JPEG only. Original videos remain local.",
        images=records,
    )
    (output / "provenance.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.suite, args.output), indent=2))


if __name__ == "__main__":
    main()
