"""Render two actual generated trajectory variants side by side, with their real LiDAR."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = ["ffmpeg"]
parser = argparse.ArgumentParser()
parser.add_argument("straight", type=Path)
parser.add_argument("left_shift", type=Path)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
bundles = [args.straight.resolve(), args.left_shift.resolve()]
manifests = [json.loads((b / "bundle_manifest.json").read_text()) for b in bundles]
trajectories = [np.load(b / "trajectory.npz") for b in bundles]
frames = manifests[0]["camera_frames"]
assert all(m["status"] == "passed" and m["camera_frames"] == frames for m in manifests)
out = args.output.resolve()
assert not out.exists()
out.mkdir(parents=True)
camera = "camera_front_wide_120fov"
caps = [cv2.VideoCapture(str(b / "cameras" / f"{camera}.mp4")) for b in bundles]
clouds = []
for b, m in zip(bundles, manifests, strict=True):
    clips = []
    for record in m["sweeps"]:
        with (b / record["file"]).open("rb") as file:
            while True:
                line = file.readline()
                assert line and file.tell() < 4096
                if line == b"end_header\n":
                    break
            points = np.frombuffer(file.read(), dtype="<f4").reshape(-1, 4)
        clips.append(points)
    clouds.append(clips)
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
        "30",
        "-i",
        "pipe:0",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(out / "trajectory_sensor_comparison.mp4"),
    ],
    stdin=subprocess.PIPE,
)
try:
    for frame in range(frames):
        canvas = np.full((720, 1248, 3), (25, 20, 16), np.uint8)
        for variant, (cap, m, traj) in enumerate(zip(caps, manifests, trajectories, strict=True)):
            ok, image = cap.read()
            assert ok
            base = 624 * variant
            canvas[30:381, base : base + 624] = cv2.resize(image, (624, 351))
            title = [
                "STRAIGHT / generated RGB + LiDAR",
                "LEFT SHIFT / generated RGB + LiDAR",
            ][variant]
            cv2.putText(
                canvas,
                title,
                (base + 14, 22),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.59,
                (235, 235, 235),
                1,
                cv2.LINE_AA,
            )
            index = max(i for i, s in enumerate(m["sweeps"]) if s["frame_id"] <= frame)
            points = clouds[variant][index]
            x = np.round(312 - points[:, 1] * 4).astype(int)
            y = np.round(655 - points[:, 0] * 4).astype(int)
            valid = (x >= 0) & (x < 624) & (y >= 390) & (y < 690)
            colors = cv2.applyColorMap(
                np.clip((points[:, 2] + 3) * 22, 0, 255).astype(np.uint8),
                cv2.COLORMAP_TURBO,
            ).reshape(-1, 3)
            canvas[y[valid], base + x[valid]] = colors[valid]
            cv2.rectangle(canvas, (base + 308, 651), (base + 316, 659), (255, 255, 255), -1)
            ego = traj["vehicle_to_world"][frame, :3, 3]
            cv2.putText(
                canvas,
                f"Input ego x={ego[0]:.2f} y={ego[1]:.2f} m | t={frame / 30:.2f}s",
                (base + 10, 712),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.49,
                (210, 230, 230),
                1,
                cv2.LINE_AA,
            )
        encoder.stdin.write(canvas.tobytes())
finally:
    encoder.stdin.close()
    for cap in caps:
        cap.release()
assert encoder.wait() == 0
subprocess.run(
    [
        *FFMPEG,
        "-v",
        "error",
        "-xerror",
        "-i",
        str(out / "trajectory_sensor_comparison.mp4"),
        "-f",
        "null",
        "-",
    ],
    check=True,
)
report = dict(
    status="generated_variant_comparison_rendered",
    camera_frames=frames,
    fps=30,
    source_bundles=[str(b) for b in bundles],
    input_ego_start_xyz_m=[t["vehicle_to_world"][0, :3, 3].tolist() for t in trajectories],
    input_ego_end_xyz_m=[t["vehicle_to_world"][frames - 1, :3, 3].tolist() for t in trajectories],
    note="Both camera/LiDAR streams are actual joint model outputs. Ego poses are input controls. Different future controls may alter even initial appearance in bidirectional generation. No measured ego-motion or physical-consistency pass claimed.",
)
(out / "comparison_manifest.json").write_text(json.dumps(report, indent=2) + "\n")
checks = []
for path in sorted(out.iterdir()):
    with path.open("rb") as file:
        digest = hashlib.file_digest(file, "sha256").hexdigest()
    checks.append(f"{digest}  {path.name}")
(out / "SHA256SUMS").write_text("\n".join(checks) + "\n")
print(out, flush=True)
