"""Validate generated sensors and build a portable, synchronized replay bundle."""

# ruff: noqa: E402 -- import the pinned Framework checkout after adding its local path.
import argparse
import csv
import hashlib
import json
import math
import shutil
import sys
import subprocess
from pathlib import Path

import numpy as np
import torch
from safetensors import safe_open

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "repos/cosmos-framework"))
from cosmos_framework.model.generator.tokenizers.lidar.geometry import (
    PANDAR128_ELEVATIONS_DEG,
    range_map_to_xyz,
)
from cosmos_framework.model.generator.tokenizers.lidar.range_projection import (
    LidarRangeProjectionConfig,
)
from cosmos_framework.inference.vision import load_conditioning_video

parser = argparse.ArgumentParser()
parser.add_argument(
    "sample",
    type=Path,
    help="Generated sample directory containing sample_outputs.json",
)
parser.add_argument(
    "--request",
    type=Path,
    required=True,
    help="Original input request, for control path resolution",
)
parser.add_argument("--scene", type=Path, help="Matching synthetic scene containing trajectory.npz")
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
sample, output, request_file = (
    args.sample.resolve(),
    args.output.resolve(),
    args.request.resolve(),
)
assert not output.exists(), "Use a fresh bundle output directory"
request = json.loads(request_file.read_text())
sample_output = json.loads((sample / "sample_outputs.json").read_text())
assert sample_output.get("status") == "success", sample_output
assert len(sample_output.get("outputs", [])) == 1, sample_output
videos = sorted(sample.glob("vision_view*.mp4"))
assert len(videos) == len(request["multiview"]["views"]), (len(videos), request)
output.mkdir(parents=True)
(output / "cameras").mkdir()
(output / "controls").mkdir()
(output / "pointclouds").mkdir()


def probe(path):
    result = json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-count_frames",
                "-show_entries",
                "stream=width,height,r_frame_rate,nb_read_frames,duration",
                "-of",
                "json",
                str(path),
            ],
            text=True,
        )
    )["streams"][0]
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-xerror",
            "-i",
            str(path),
            "-f",
            "null",
            "-",
        ],
        check=True,
    )
    return result


camera_reports = []
image_geometry = {}
frame_count = None
for path in videos:
    camera = path.stem.split("_", 2)[2]
    view = next(view for view in request["multiview"]["views"] if view["camera_key"] == camera)
    stream = probe(path)
    frames = int(stream["nb_read_frames"])
    assert frames == (frame_count or frames) and stream["r_frame_rate"] == "30/1", stream
    assert frames == request["num_frames"], (stream, request["num_frames"])
    frame_count = frames
    shutil.copy2(path, output / "cameras" / f"{camera}.mp4")
    control = (request_file.parent / view["control_path"]).resolve()
    # Use the inference loader's aspect-preserving resize and center crop, not a direct stretch.
    pixels = load_conditioning_video(
        control, target_h=stream["height"], target_w=stream["width"], max_frames=frames
    )
    rgb = ((pixels + 1) * 127.5).round().clamp(0, 255).to(dtype=torch.uint8)
    rgb = rgb.permute(1, 2, 3, 0).contiguous().numpy()
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "rawvideo",
            "-pixel_format",
            "rgb24",
            "-video_size",
            f"{stream['width']}x{stream['height']}",
            "-framerate",
            "30",
            "-i",
            "pipe:0",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output / "controls" / f"{camera}.mp4"),
        ],
        input=rgb.tobytes(),
        check=True,
    )
    del pixels, rgb
    source_stream = json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=width,height",
                "-of",
                "json",
                str(control),
            ],
            text=True,
        )
    )["streams"][0]
    source_w, source_h = source_stream["width"], source_stream["height"]
    scale = max(stream["width"] / source_w, stream["height"] / source_h)
    resized_w, resized_h = math.ceil(scale * source_w), math.ceil(scale * source_h)
    crop_x, crop_y = (
        round((resized_w - stream["width"]) / 2),
        round((resized_h - stream["height"]) / 2),
    )
    affine = np.array(
        [
            [resized_w / source_w, 0, (resized_w / source_w - 1) / 2 - crop_x],
            [0, resized_h / source_h, (resized_h / source_h - 1) / 2 - crop_y],
            [0, 0, 1],
        ]
    )
    image_geometry[camera] = dict(
        control_wh=[source_w, source_h],
        resized_wh=[resized_w, resized_h],
        center_crop_xy=[crop_x, crop_y],
        output_wh=[stream["width"], stream["height"]],
        control_pixel_to_output_pixel=affine.tolist(),
        convention="Pixel centers; same resize dimensions and center crop as inference vision.py; stored WSM uses lossy visualization encoding",
    )
    camera_reports.append(dict(camera=camera, stream=stream, full_decode=True))

with safe_open(str(sample / "lidar.safetensors"), framework="numpy") as file:
    assert set(file.keys()) == {"range_m", "intensity", "frame_ids"}
    ranges, intensities, ids = (
        file.get_tensor(key) for key in ["range_m", "intensity", "frame_ids"]
    )
assert ranges.shape == intensities.shape and tuple(ranges.shape[1:]) == (128, 1800)
assert ids.shape == (ranges.shape[0],) and len(ids) > 1
assert np.all(np.diff(ids) == 3) and ids[0] == 0 and ids[-1] < frame_count
assert np.isfinite(ranges).all() and np.isfinite(intensities).all()
assert ((ranges == 0) | ((ranges >= 5) & (ranges <= 100))).all()
assert ((intensities >= 0) & (intensities <= 1)).all()
checkpoint_config = json.loads(
    (ROOT / "storage/models/Cosmos3-Nano-Transfer-Auto/config.json").read_text()
)
projection_data = dict(checkpoint_config["model"]["config"]["lidar_tokenizer"]["range_projection"])
projection_data.pop("_target", None)
projection = LidarRangeProjectionConfig.from_dict(projection_data)
lidar_calibration = dict(
    range_projection=projection.to_dict(),
    beam_elevations_degrees=list(PANDAR128_ELEVATIONS_DEG),
    source="Cosmos Framework geometry.py, native LiDARGen Pandar128 beam order",
    azimuth_columns_note="Semantic ray columns advance from +180 degrees toward -180 degrees, endpoint excluded; native nearest-return pooling factor 2",
    angular_calibration_scope="Published tokenizer projection calibration, not a measured per-device calibration",
)
(output / "lidar_calibration.json").write_text(json.dumps(lidar_calibration, indent=2) + "\n")
trajectory = None
if args.scene:
    scene = args.scene.resolve()
    assert request_file.parent == scene, "Scene must match the original request"
    trajectory = np.load(scene / "trajectory.npz", allow_pickle=False)
    assert len(trajectory["vehicle_to_world"]) > ids[-1]
    for filename in ["trajectory.npz", "trajectory.csv", "scene_manifest.json"]:
        shutil.copy2(scene / filename, output / filename)
    with (output / "synchronized_frames.csv").open("w") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "camera_frame_id",
                "timestamp_s",
                "lidar_frame_id_held",
                "ego_x_m",
                "ego_y_m",
                "ego_z_m",
                "ego_yaw_rad",
                "lead_x_m",
                "lead_y_m",
                "lead_z_m",
            ]
        )
        for frame in range(frame_count):
            pose = trajectory["vehicle_to_world"][frame]
            lead = trajectory["lead_car_to_world"][frame]
            held = int(ids[np.searchsorted(ids, frame, side="right") - 1])
            writer.writerow(
                [
                    frame,
                    float(trajectory["timestamps_s"][frame]),
                    held,
                    *pose[:3, 3],
                    float(np.arctan2(pose[1, 0], pose[0, 0])),
                    *lead[:3, 3],
                ]
            )
    shutil.copytree(scene / "rig", output / "rig")
    manifest = json.loads((scene / "scene_manifest.json").read_text())
    calibration_path = ROOT / manifest["camera_calibration_source"]
    shutil.copy2(calibration_path, output / "camera_calibration.json")
    rig = json.loads(calibration_path.read_text())
    for camera, info in image_geometry.items():
        native = rig[camera]["ftheta_intrinsics"]
        ratio = 720 / native[3]  # renderer's fixed resize_1280x720 recipe
        rendered_w, rendered_h = int(native[2] * ratio), int(native[3] * ratio)
        source_w, source_h = info["control_wh"]
        prepare_affine = np.array(
            [
                [source_w / rendered_w, 0, (source_w / rendered_w - 1) / 2],
                [0, source_h / rendered_h, (source_h / rendered_h - 1) / 2],
                [0, 0, 1],
            ]
        )
        native_affine = np.diag([ratio, ratio, 1.0])
        info["native_projection_to_output_pixel"] = (
            np.asarray(info["control_pixel_to_output_pixel"]) @ prepare_affine @ native_affine
        ).tolist()
        info["renderer_ftheta_scale"] = ratio
        info["renderer_raster_wh_before_prepare_output"] = [rendered_w, rendered_h]
        info["calibration_note"] = (
            "camera_calibration.json is native FTheta calibration. Apply native_projection_to_output_pixel after native camera projection. This describes control geometry, not a measured calibration of generated RGB."
        )
    # Include compact structured inputs so the bundle carries actor geometry and map provenance.
    for directory in [
        "all_object_info",
        "vehicle_pose",
        "pose",
        "ftheta_intrinsic",
        "3d_lanelines",
        "3d_road_boundaries",
        "3d_poles",
        "3d_crosswalks",
        "3d_road_markings",
        "3d_traffic_lights",
        "3d_traffic_lights_lightnet_status",
        "3d_traffic_signs",
        "3d_wait_lines",
        "captions",
    ]:
        shutil.copytree(scene / directory, output / "scenario_inputs" / directory)
(output / "camera_image_geometry.json").write_text(json.dumps(image_geometry, indent=2) + "\n")
cloud_preview, sweeps = [], []
for index, frame_id in enumerate(ids):
    xyz, ray_ids = range_map_to_xyz(ranges[index], ranges[index] > 0, range_projection=projection)
    assert len(xyz) > 100, f"Empty or nearly empty generated sweep {index}"
    intensity = intensities[index].reshape(-1)[ray_ids].astype(np.float32)
    np.testing.assert_allclose(
        np.linalg.norm(xyz, axis=1),
        ranges[index].reshape(-1)[ray_ids],
        rtol=1e-5,
        atol=1e-4,
    )
    points = np.column_stack((xyz, intensity)).astype("<f4")
    filename = f"{int(frame_id):06d}.ply"
    header = (
        f"ply\nformat binary_little_endian 1.0\nelement vertex {len(points)}\n"
        "property float x\nproperty float y\nproperty float z\nproperty float intensity\nend_header\n"
    )
    with (output / "pointclouds" / filename).open("wb") as file:
        file.write(header.encode("ascii"))
        file.write(points.tobytes())
    subset = points[np.linspace(0, len(points) - 1, min(3500, len(points)), dtype=int)]
    cloud_preview.append(np.round(subset, 3).tolist())
    record = dict(
        frame_id=int(frame_id),
        timestamp_s=float(frame_id / 30),
        points=len(points),
        file=f"pointclouds/{filename}",
    )
    if trajectory is not None:
        end_id = min(int(frame_id) + 3, len(trajectory["timestamps_s"]) - 1)
        record["lidar_to_world_start"] = (
            trajectory["vehicle_to_world"][frame_id] @ trajectory["lidar_to_vehicle"]
        ).tolist()
        record["lidar_to_world_end"] = (
            trajectory["vehicle_to_world"][end_id] @ trajectory["lidar_to_vehicle"]
        ).tolist()
        record["timestamp_end_s"] = float(trajectory["timestamps_s"][end_id])
    sweeps.append(record)
shutil.copy2(sample / "lidar.safetensors", output / "lidar.safetensors")
shutil.copy2(sample / "sample_args.json", output / "sample_args.json")
shutil.copy2(sample / "sample_outputs.json", output / "sample_outputs.json")
shutil.copy2(request_file, output / "source_request.json")
replay = dict(
    cameras=[row["camera"] for row in camera_reports],
    frames=frame_count,
    fps=30,
    frame_ids=ids.tolist(),
    clouds=cloud_preview,
    trajectory=None,
    title=request["name"],
)
if trajectory is not None:
    replay["trajectory"] = dict(
        ego=trajectory["vehicle_to_world"][:frame_count, :3, 3].round(4).tolist(),
        lead=trajectory["lead_car_to_world"][:frame_count, :3, 3].round(4).tolist(),
    )
template = (ROOT / "scripts/replay_template.html").read_text()
(output / "index.html").write_text(
    template.replace("__REPLAY_DATA__", json.dumps(replay, separators=(",", ":")))
)
shutil.copy2(ROOT / "scripts/serve_replay.py", output / "serve_replay.py")
report = dict(
    status="passed",
    model="Cosmos3-Nano-Transfer-Auto",
    camera_fps=30,
    lidar_fps=10,
    camera_frames=frame_count,
    cameras=camera_reports,
    lidar_shape=list(ranges.shape),
    sweeps=sweeps,
    range_projection=projection.to_dict(),
    lidar_coordinates="sensor FLU, metres; native spinning sweep, no per-point deskew",
    pose_provenance="Input synthetic trajectory, not model-estimated odometry"
    if trajectory is not None
    else "Numeric source poses not included in reference sample",
    sensor_scope="Generated RGB and LiDAR range/intensity; no radar/GNSS/IMU simulation",
    validation_scope="Decode, clock alignment, finite physical values and calibrated XYZ round trip; no physical-consistency KPI pass claimed",
)
report["source_request_note"] = (
    "Provenance only: paths in source_request.json/sample_args.json refer to the original project; bundle replay is standalone."
)
if trajectory is not None:
    report["trajectory_scope"] = dict(
        input_pose_frames=len(trajectory["timestamps_s"]),
        generated_camera_frames=frame_count,
        generated_camera_timestamp_span_s=[0, float((frame_count - 1) / 30)],
        actual_ego_start_xyz_m=trajectory["vehicle_to_world"][0, :3, 3].tolist(),
        actual_ego_end_xyz_m=trajectory["vehicle_to_world"][frame_count - 1, :3, 3].tolist(),
        note="trajectory.csv/npz preserve the full source trajectory; synchronized_frames.csv identifies only generated camera frames. All poses are input controls.",
    )
(output / "bundle_manifest.json").write_text(json.dumps(report, indent=2) + "\n")
(output / "README.md").write_text(
    "# Cosmos 轨迹驱动传感器输出\n\n"
    f"七路 RGB，各 {frame_count} 帧 / 30 FPS；LiDAR {len(ids)} 次扫描 / 10 Hz。"
    "RGB 与 LiDAR 来自同一次联合采样，位姿来自输入轨迹。\n\n"
    "运行 `python serve_replay.py --port 8080`，打开 http://127.0.0.1:8080 。"
    "也可直接播放 review/sensor_mosaic.mp4。\n\n"
    "cameras/：生成 RGB；controls/：输入 WSM 对照；pointclouds/：完整二进制 PLY XYZI；"
    "lidar.safetensors：range_m / intensity / frame_ids；bundle_manifest.json：时间戳与校验信息。"
    "点云为传感器 FLU、米，未逐点去畸变；无效射线距离为 0。\n\n"
    "trajectory.npz/csv 保留源轨迹，synchronized_frames.csv 只列已生成帧。"
    "输入相机与 LiDAR 标定及像素变换分别见 camera_calibration.json / lidar_calibration.json / camera_image_geometry.json。\n\n"
    "这是开环生成式传感器仿真，尚无驾驶策略与动力学闭环，也未模拟 Radar / GNSS / IMU。"
    "几何控制误差见 review/control_depth_agreement.json；生成数据与输入标注不应直接当作高精度真值。\n\n"
    "SHA256SUMS 记录整个文件包。source_request.json / sample_args.json 中路径是原项目来源记录，"
    "回放不依赖原路径，但再次推理需要恢复项目和相应输入。\n"
)
checksums = []
for path in sorted(output.rglob("*")):
    if path.is_file():
        with path.open("rb") as file:
            digest = hashlib.file_digest(file, "sha256").hexdigest()
        checksums.append(f"{digest}  {path.relative_to(output)}")
(output / "SHA256SUMS").write_text("\n".join(checksums) + "\n")
print(
    json.dumps(
        {
            "status": "passed",
            "bundle": str(output),
            "camera_frames": frame_count,
            "lidar_sweeps": len(ids),
        },
        indent=2,
    ),
    flush=True,
)
