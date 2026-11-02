"""Make real sensor contact sheets, a synchronized mosaic and temporal diagnostics."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = ["ffmpeg"]

parser = argparse.ArgumentParser()
parser.add_argument("bundle", type=Path)
args = parser.parse_args()
bundle = args.bundle.resolve()
manifest = json.loads((bundle / "bundle_manifest.json").read_text())
output = bundle / "review"
output.mkdir(exist_ok=True)
cameras = [row["camera"] for row in manifest["cameras"]]
frames = manifest["camera_frames"]
fps = manifest["camera_fps"]
selected = [0, (frames - 1) // 2, frames - 1]
captures = [cv2.VideoCapture(str(bundle / "cameras" / f"{camera}.mp4")) for camera in cameras]
controls = [cv2.VideoCapture(str(bundle / "controls" / f"{camera}.mp4")) for camera in cameras]
assert all(cap.isOpened() for cap in captures + controls)
snapshots, overlays = {}, {}
previous = [None] * len(cameras)
changes = [[] for _ in cameras]
trajectory = np.load(bundle / "trajectory.npz") if (bundle / "trajectory.npz").exists() else None


def load_ply(path, count):
    with path.open("rb") as file:
        while True:
            line = file.readline()
            assert line, f"Missing PLY header in {path}"
            if line == b"end_header\n":
                break
            assert file.tell() < 4096, path
        points = np.frombuffer(file.read(), dtype="<f4").reshape(-1, 4)
    assert len(points) == count and np.isfinite(points).all(), path
    return points


clouds = [load_ply(bundle / sweep["file"], sweep["points"]) for sweep in manifest["sweeps"]]


def label(image, text):
    image = image.copy()
    cv2.rectangle(image, (0, 0), (image.shape[1], 27), (15, 22, 30), -1)
    cv2.putText(
        image,
        text,
        (7, 19),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.42,
        (230, 240, 245),
        1,
        cv2.LINE_AA,
    )
    return image


def bev(points):
    img = np.full((240, 416, 3), (20, 17, 13), np.uint8)
    for axis in range(-40, 41, 10):
        cv2.line(img, (208 + axis * 4, 0), (208 + axis * 4, 239), (47, 42, 35), 1)
        cv2.line(img, (0, 210 - axis * 4), (415, 210 - axis * 4), (47, 42, 35), 1)
    px = np.round(208 - points[:, 1] * 4).astype(int)
    py = np.round(210 - points[:, 0] * 4).astype(int)
    valid = (px >= 0) & (px < 416) & (py >= 27) & (py < 240)
    color = cv2.applyColorMap(
        np.clip((points[:, 2] + 3) * 22, 0, 255).astype(np.uint8), cv2.COLORMAP_TURBO
    ).reshape(-1, 3)
    img[py[valid], px[valid]] = color[valid]
    cv2.rectangle(img, (204, 206), (212, 214), (255, 255, 255), -1)
    return label(img, "Generated LiDAR XY / 10 m grid")


def trajectory_panel(frame):
    img = np.full((240, 416, 3), (20, 17, 13), np.uint8)
    if trajectory is None:
        cv2.putText(
            img,
            "Numeric poses not provided",
            (22, 100),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (200, 210, 220),
            1,
        )
    else:
        ego = trajectory["vehicle_to_world"][:frames, :2, 3]
        lead = trajectory["lead_car_to_world"][:frames, :2, 3]
        both = np.concatenate((ego, lead))
        low, high = both.min(axis=0) - [3, 4], both.max(axis=0) + [3, 4]
        for path, color in [(ego, (220, 230, 100)), (lead, (100, 160, 255))]:
            pixel = np.round((path - low) / (high - low) * [360, -140] + [28, 195]).astype(np.int32)
            cv2.polylines(img, [pixel], False, color, 2, cv2.LINE_AA)
            cv2.circle(img, tuple(pixel[frame]), 5, color, -1)
        cv2.putText(
            img,
            f"Ego x={ego[frame, 0]:.2f} y={ego[frame, 1]:.2f} m",
            (15, 55),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (220, 230, 100),
            1,
        )
    cv2.putText(
        img,
        f"t={frame / fps:.2f}s  frame={frame}",
        (15, 222),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        (235, 235, 235),
        1,
    )
    return label(img, "Input trajectory / not estimated odometry")


encoder = subprocess.Popen(
    [
        *FFMPEG,
        "-y",
        "-v",
        "error",
        "-f",
        "rawvideo",
        "-pixel_format",
        "bgr24",
        "-video_size",
        "1248x720",
        "-framerate",
        str(fps),
        "-i",
        "pipe:0",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "19",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output / "sensor_mosaic.mp4"),
    ],
    stdin=subprocess.PIPE,
)
try:
    for frame in range(frames):
        cells = []
        for index, (camera, cap, ctrl) in enumerate(zip(cameras, captures, controls, strict=True)):
            ok, image = cap.read()
            control_ok, control = ctrl.read()
            assert ok and control_ok, (camera, frame)
            small = cv2.resize(image, (208, 120))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)
            if previous[index] is not None:
                changes[index].append(float(np.abs(gray - previous[index]).mean()))
            previous[index] = gray
            if frame in selected:
                snapshots[(index, frame)] = cv2.resize(image, (416, 240))
                control = cv2.resize(control, (image.shape[1], image.shape[0]))
                mask = np.max(control, axis=2) > 45
                blended = image.copy()
                blended[mask] = (0.45 * image[mask] + 0.55 * control[mask]).astype(np.uint8)
                overlays[(index, frame)] = cv2.resize(blended, (416, 240))
            cells.append(label(cv2.resize(image, (416, 240)), camera))
        sweep = max(i for i, row in enumerate(manifest["sweeps"]) if row["frame_id"] <= frame)
        cells += [bev(clouds[sweep]), trajectory_panel(frame)]
        mosaic = np.vstack([np.hstack(cells[i : i + 3]) for i in range(0, 9, 3)])
        encoder.stdin.write(mosaic.tobytes())
finally:
    encoder.stdin.close()
    for cap in captures + controls:
        cap.release()
assert encoder.wait() == 0
for data, filename in [
    (snapshots, "camera_contact_sheet.jpg"),
    (overlays, "wsm_overlay_contact_sheet.jpg"),
]:
    sheet = Image.new("RGB", (1248, 270 * len(cameras)), "#10151c")
    draw = ImageDraw.Draw(sheet)
    for index, camera in enumerate(cameras):
        for column, frame in enumerate(selected):
            draw.text(
                (column * 416 + 8, index * 270 + 6),
                f"{camera} | {frame / fps:.2f}s",
                fill="white",
            )
            sheet.paste(
                Image.fromarray(cv2.cvtColor(data[(index, frame)], cv2.COLOR_BGR2RGB)),
                (column * 416, index * 270 + 30),
            )
    sheet.save(output / filename, quality=92)
lidar_sheet = np.hstack(
    [
        bev(
            clouds[
                min(
                    range(len(clouds)),
                    key=lambda i: abs(manifest["sweeps"][i]["frame_id"] - frame),
                )
            ]
        )
        for frame in selected
    ]
)
cv2.imwrite(str(output / "lidar_bev.jpg"), lidar_sheet)
report = dict(
    camera_temporal_mae_8bit={
        camera: dict(mean=float(np.mean(values)), max=float(max(values)))
        for camera, values in zip(cameras, changes, strict=True)
    },
    lidar_points_per_sweep=[len(cloud) for cloud in clouds],
    note="Temporal pixel changes document output dynamics, not accuracy of trajectory adherence. WSM overlays require visual inspection; no physical consistency KPI claimed.",
)
(output / "temporal_diagnostics.json").write_text(json.dumps(report, indent=2) + "\n")
subprocess.run(
    [
        *FFMPEG,
        "-v",
        "error",
        "-xerror",
        "-i",
        str(output / "sensor_mosaic.mp4"),
        "-f",
        "null",
        "-",
    ],
    check=True,
)
# Keep the complete bundle integrity inventory valid after adding review artifacts.
checksums = []
for path in sorted(bundle.rglob("*")):
    if path.is_file() and path.name != "SHA256SUMS":
        with path.open("rb") as file:
            digest = hashlib.file_digest(file, "sha256").hexdigest()
        checksums.append(f"{digest}  {path.relative_to(bundle)}")
(bundle / "SHA256SUMS").write_text("\n".join(checksums) + "\n")
print(output, flush=True)
