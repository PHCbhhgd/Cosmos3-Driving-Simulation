"""Compare generated RGB with aligned WSM controls over an event window.

Crops are manually chosen review regions, not detector predictions. Controls
describe requested geometry, not measured calibration of generated imagery.
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageOps

from build_release import digest


def review(bundle, output, camera, frames, crop=None):
    manifest = json.loads((bundle / "bundle_manifest.json").read_text())
    geometry = json.loads((bundle / "camera_image_geometry.json").read_text())[camera]
    rgb_path = bundle / "cameras" / f"{camera}.mp4"
    control_path = bundle / "controls" / f"{camera}.mp4"
    frames = sorted(set(frames))
    if not frames or frames[0] < 0 or frames[-1] >= manifest["camera_frames"]:
        raise ValueError("Frame IDs must lie within the generated video")
    width, height = geometry["output_wh"]
    x, y, w, h = crop or (0, 0, width, height)
    if min(x, y) < 0 or min(w, h) <= 0 or x + w > width or y + h > height:
        raise ValueError("Crop must be nonempty and inside the output image")
    output.mkdir(parents=True, exist_ok=False)
    captures = [cv2.VideoCapture(str(p)) for p in [rgb_path, control_path]]
    if not all(cap.isOpened() for cap in captures):
        raise ValueError("Unable to open RGB or control video")
    transform = np.asarray(geometry["control_pixel_to_output_pixel"])
    cells = []
    try:
        for index in frames:
            decoded = []
            for cap in captures:
                cap.set(cv2.CAP_PROP_POS_FRAMES, index)
                ok, frame = cap.read()
                if not ok:
                    raise ValueError(f"Unable to decode frame {index}")
                decoded.append(frame)
            decoded[1] = cv2.warpAffine(decoded[1], transform[:2], (width, height))
            tile = Image.new("RGB", (416, 534), (15, 22, 30))
            draw = ImageDraw.Draw(tile)
            for row, (label, frame) in enumerate(zip(["GENERATED RGB", "INPUT WSM"], decoded)):
                image = Image.fromarray(
                    cv2.cvtColor(frame[y : y + h, x : x + w], cv2.COLOR_BGR2RGB)
                )
                image.save(output / f"frame-{index:06d}-{row}.jpg", quality=95)
                tile.paste(ImageOps.pad(image, (416, 240), color=(15, 22, 30)), (0, row * 267 + 27))
                draw.text(
                    (8, row * 267 + 7),
                    f"{label} | f{index} | {index / manifest['camera_fps']:.3f}s",
                    fill="white",
                )
            cells.append(tile)
    finally:
        for cap in captures:
            cap.release()
    columns = min(4, len(cells))
    sheet = Image.new("RGB", (416 * columns, 534 * ((len(cells) + columns - 1) // columns)))
    for i, tile in enumerate(cells):
        sheet.paste(tile, ((i % columns) * 416, (i // columns) * 534))
    sheet.save(output / "event-window.jpg", quality=95)
    report = dict(
        scope=__doc__.strip(),
        camera=camera,
        frame_ids=frames,
        timestamps_s=[i / manifest["camera_fps"] for i in frames],
        crop_output_xywh=[x, y, w, h],
        generated_video_sha256=digest(rgb_path),
        control_video_sha256=digest(control_path),
        control_pixel_to_output_pixel=transform.tolist(),
        sheet_sha256=digest(output / "event-window.jpg"),
        display="Paired RGB/input crops, letterboxed with ordinary resizing; no enhancement",
    )
    (output / "event-window.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("bundle", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--camera", default="camera_front_wide_120fov")
    p.add_argument("--frames", type=int, nargs="+", required=True)
    p.add_argument("--crop", type=int, nargs=4, metavar=("X", "Y", "WIDTH", "HEIGHT"))
    args = p.parse_args()
    print(
        json.dumps(review(args.bundle, args.output, args.camera, args.frames, args.crop), indent=2)
    )


if __name__ == "__main__":
    main()
