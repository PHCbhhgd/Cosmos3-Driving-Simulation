"""Compare generated RGB with the exact aligned control video saved by Framework."""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

from build_release import digest


def review(folder, output, frames):
    run = json.loads((folder / "run.json").read_text())
    if run["status"] != "generated_and_decoded":
        raise ValueError("Require a completed and fully decoded duration run")
    raw = folder / "raw" / run["case"]
    rgb = list(raw.glob("vision_*.mp4"))
    control = list(raw.glob("control_*.mp4"))
    if len(rgb) != 1 or len(control) != 1:
        raise ValueError("Require one generated and one aligned Framework control video")
    captures = [cv2.VideoCapture(str(p)) for p in [rgb[0], control[0]]]
    meta = [
        (
            int(c.get(cv2.CAP_PROP_FRAME_COUNT)),
            c.get(cv2.CAP_PROP_FPS),
            int(c.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(c.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        )
        for c in captures
    ]
    if not all(c.isOpened() for c in captures) or meta[0] != meta[1]:
        raise ValueError("Generated RGB and Framework control clocks/dimensions disagree")
    count, fps, _, _ = meta[0]
    if count != run["expected_frames"] or any(i < 0 or i >= count for i in frames):
        raise ValueError("Frame IDs exceed the validated output")
    output.mkdir(parents=True, exist_ok=False)
    tiles = []
    try:
        for index in sorted(set(frames)):
            images = []
            for cap in captures:
                cap.set(cv2.CAP_PROP_POS_FRAMES, index)
                ok, frame = cap.read()
                if not ok:
                    raise ValueError(f"Could not read frame {index}")
                images.append(frame)
            mask = np.max(images[1], axis=2) > 45
            overlay = images[0].copy()
            overlay[mask] = (0.45 * overlay[mask] + 0.55 * images[1][mask]).astype(np.uint8)
            tile = Image.new("RGB", (416, 801), (15, 22, 30))
            for row, (label, frame) in enumerate(
                zip(["GENERATED RGB", "INPUT WSM", "OVERLAY"], [*images, overlay])
            ):
                tile.paste(
                    Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).resize((416, 240)),
                    (0, 267 * row + 27),
                )
                ImageDraw.Draw(tile).text(
                    (8, 267 * row + 7), f"{label} | f{index} | {index / fps:.3f}s", fill="white"
                )
            tiles.append(tile)
    finally:
        for cap in captures:
            cap.release()
    columns = min(4, len(tiles))
    sheet = Image.new("RGB", (416 * columns, 801 * ((len(tiles) + columns - 1) // columns)))
    for i, tile in enumerate(tiles):
        sheet.paste(tile, (416 * (i % columns), 801 * (i // columns)))
    sheet.save(output / "rgb-control.jpg", quality=93)
    report = dict(
        case=run["case"],
        frame_ids=sorted(set(frames)),
        fps=fps,
        rgb_sha256=digest(rgb[0]),
        control_sha256=digest(control[0]),
        scope=__doc__.strip(),
        alignment="Use original saved Framework control; no further crop/retiming",
        sheet_sha256=digest(output / "rgb-control.jpg"),
    )
    (output / "rgb-control.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("folder", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--frames", type=int, nargs="+", required=True)
    args = p.parse_args()
    print(json.dumps(review(args.folder, args.output, args.frames), indent=2))


if __name__ == "__main__":
    main()
