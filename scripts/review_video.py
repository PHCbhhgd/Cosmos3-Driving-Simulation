"""Fully decode a video and export timestamped frames and descriptive diagnostics.

Pixel-change statistics describe the encoded video, not physical world stability.
The contact sheet supports human review; no automatic quality pass is inferred.
"""

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw


def review(video, output, interval=1.0, expected_frames=None, extra_frames=()):
    if interval <= 0:
        raise ValueError("interval must be positive")
    output.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise ValueError(f"Cannot open {video}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        raise ValueError("Video has no valid FPS")
    declared = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    selected = set(range(0, declared, max(1, round(interval * fps)))) | {declared - 1}
    if any(frame < 0 or frame >= declared for frame in extra_frames):
        raise ValueError("Extra review frames must lie within the video")
    selected.update(extra_frames)
    images, changes, brightness, sharpness = [], [], [], []
    previous = None
    count = 0
    dimensions = None
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        dimensions = [frame.shape[1], frame.shape[0]]
        small = cv2.resize(frame, (208, 120)).astype(np.float32) / 255
        gray = cv2.cvtColor((small * 255).astype(np.uint8), cv2.COLOR_BGR2GRAY)
        brightness.append(float(gray.mean() / 255))
        sharpness.append(float(cv2.Laplacian(gray, cv2.CV_32F).var()))
        if previous is not None:
            changes.append(
                dict(
                    frame_id=count,
                    timestamp_s=count / fps,
                    mean_abs_rgb_change=float(np.abs(small - previous).mean()),
                )
            )
        previous = small
        if count in selected:
            image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            image.save(output / f"frame-{count:06d}.jpg", quality=92)
            thumb = image.resize((416, 240))
            tile = Image.new("RGB", (416, 267), (15, 22, 30))
            tile.paste(thumb, (0, 27))
            ImageDraw.Draw(tile).text((8, 7), f"frame {count} | t={count / fps:.3f}s", fill="white")
            images.append(tile)
        count += 1
    cap.release()
    if count != declared or (expected_frames is not None and count != expected_frames):
        raise ValueError(f"Decoded {count}, declared {declared}, expected {expected_frames}")
    if not count:
        raise ValueError("Empty video")
    columns = min(4, len(images))
    sheet = Image.new(
        "RGB", (416 * columns, 267 * ((len(images) + columns - 1) // columns)), (15, 22, 30)
    )
    for i, tile in enumerate(images):
        sheet.paste(tile, ((i % columns) * 416, (i // columns) * 267))
    sheet.save(output / "timeline.jpg", quality=92)
    with video.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    report = dict(
        video=video.name,
        sha256=digest,
        full_decode=True,
        frames=count,
        fps=fps,
        dimensions=dimensions,
        encoded_duration_s=count / fps,
        last_frame_timestamp_s=(count - 1) / fps,
        selected_frame_ids=sorted(selected),
        mean_brightness_by_frame=brightness,
        laplacian_variance_by_frame=sharpness,
        largest_pixel_changes=sorted(changes, key=lambda r: r["mean_abs_rgb_change"], reverse=True)[
            :10
        ],
        scope="Integrity and descriptive pixel statistics only. Motion, lighting and cuts "
        "can change these values; they do not establish physical stability.",
    )
    (output / "video_diagnostics.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("video", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--interval", type=float, default=1.0)
    p.add_argument("--expected-frames", type=int)
    p.add_argument("--extra-frames", type=int, nargs="*", default=[])
    args = p.parse_args()
    result = review(args.video, args.output, args.interval, args.expected_frames, args.extra_frames)
    print(json.dumps({k: result[k] for k in ["frames", "fps", "full_decode", "sha256"]}, indent=2))


if __name__ == "__main__":
    main()
