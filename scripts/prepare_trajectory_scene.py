"""Create explicit synthetic trajectories, maps and reference-camera RDS-HQ inputs."""

import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
WSM = ROOT / "repos/cosmos-framework/.agents/skills/cookbooks/cosmos3/simulation/auto/wsm"
parser = argparse.ArgumentParser()
parser.add_argument("--variant", choices=["straight", "lane_change"], required=True)
parser.add_argument("--frames", type=int, default=121)
args = parser.parse_args()
assert args.frames >= 61 and (args.frames - 1) % 4 == 0
scene = ROOT / "storage/scenarios" / args.variant
assert not scene.exists(), f"Preserve existing scene: {scene}"
spec = importlib.util.spec_from_file_location(
    "rds_hq_io", WSM / "skills/scenario-to-rds-hq/scripts/rds_hq_io.py"
)
io = importlib.util.module_from_spec(spec)
spec.loader.exec_module(io)
rig_path = WSM / "skills/scenario-to-rds-hq/assets/hyperion8.json"
rig = json.loads(rig_path.read_text())
cameras = [
    "camera_front_wide_120fov",
    "camera_cross_left_120fov",
    "camera_cross_right_120fov",
    "camera_rear_left_70fov",
    "camera_rear_right_70fov",
    "camera_rear_tele_30fov",
    "camera_front_tele_30fov",
]
time = np.arange(args.frames + 3, dtype=np.float64) / 30
duration = (args.frames - 1) / 30
u = np.clip(time / duration, 0, 1)
y = (2.0 if args.variant == "lane_change" else 0.0) * (10 * u**3 - 15 * u**4 + 6 * u**5)
dy = (
    (2.0 if args.variant == "lane_change" else 0.0) / duration * (30 * u**2 - 60 * u**3 + 30 * u**4)
)
yaw = np.arctan2(dy, 4.0)
vehicle = np.tile(np.eye(4), (len(time), 1, 1))
vehicle[:, 0, 3] = 4 * time
vehicle[:, 1, 3] = y
vehicle[:, 0, 0] = vehicle[:, 1, 1] = np.cos(yaw)
vehicle[:, 1, 0] = np.sin(yaw)
vehicle[:, 0, 1] = -np.sin(yaw)
assert np.allclose(vehicle[0], np.eye(4))


def polyline(vertices, attributes):
    return {
        "labelData": {"shape3d": {"polyline3d": {"vertices": vertices}, "attributes": attributes}}
    }


layers = {layer: {"labels": []} for layer in io.MAP_GEOMETRY}
layers["3d_road_boundaries"]["labels"] = [
    polyline([[-30, side, 0], [100, side, 0]], [{"name": "boundary_type", "text": "curb"}])
    for side in [-5.5, 5.5]
]
layers["3d_lanelines"]["labels"] = [
    polyline(
        [[-30, side, 0], [100, side, 0]],
        [
            {"name": "colors", "enumsList": {"enumsList": ["WHITE"]}},
            {"name": "styles", "enumsList": {"enumsList": ["LONG_DASHED_SINGLE"]}},
        ],
    )
    for side in [-1.75, 1.75]
]
layers["3d_poles"]["labels"] = [
    polyline([[x, side, 0], [x, side, 5]], []) for side in [-5.5, 5.5] for x in [5, 20, 35, 50, 65]
]
objects, actor_poses = [], []
for t in time:
    lead, parked = np.eye(4), np.eye(4)
    lead[:3, 3] = [24 + 3 * t, 0, 0.8]
    parked[:3, 3] = [12, -4.3, 0.8]
    actor_poses.append(lead)
    objects.append(
        {
            "lead_car": {
                "object_type": "Car",
                "object_is_moving": True,
                "object_lwh": [4.5, 1.8, 1.6],
                "object_to_world": lead.tolist(),
            },
            "parked_car": {
                "object_type": "Car",
                "object_is_moving": False,
                "object_lwh": [4.5, 1.8, 1.6],
                "object_to_world": parked.tolist(),
            },
        }
    )
report = io.write_clip(
    scene,
    args.variant,
    {c: vehicle @ np.asarray(rig[c]["camera_to_vehicle"]) for c in cameras},
    {c: np.asarray(rig[c]["ftheta_intrinsics"]) for c in cameras},
    objects,
    layers,
    {"state_to_legacy_render_state": {}, "traffic_light_states": {}},
    camera_type="ftheta",
)
io.write_archive(
    scene / "vehicle_pose" / f"{args.variant}.tar",
    args.variant,
    {f"{i:06d}.vehicle_pose.npy": pose for i, pose in enumerate(vehicle)},
)
(scene / "rig").mkdir()
lidar_mount = np.eye(4)
lidar_mount[:3, 3] = [1.1, 0, 1.9]
(scene / "rig" / f"{args.variant}.json").write_text(
    json.dumps(
        {
            "rig": {
                "sensors": [
                    {
                        "name": "lidar:gt:top:p128",
                        "nominalSensor2Rig_FLU": {"roll-pitch-yaw": [0, 0, 0], "t": [1.1, 0, 1.9]},
                    }
                ]
            }
        },
        indent=2,
    )
    + "\n"
)
np.savez_compressed(
    scene / "trajectory.npz",
    timestamps_s=time,
    vehicle_to_world=vehicle,
    lead_car_to_world=np.array(actor_poses),
    lidar_to_vehicle=lidar_mount,
)
with (scene / "trajectory.csv").open("w") as f:
    writer = csv.writer(f)
    writer.writerow(
        ["frame_id", "timestamp_s", "ego_x_m", "ego_y_m", "ego_yaw_rad", "lead_car_x_m"]
    )
    writer.writerows(zip(range(len(time)), time, 4 * time, y, yaw, 24 + 3 * time))
captions = scene / "captions"
captions.mkdir()
# Desired synthetic appearance. Side/rear descriptions reflect actual visible geometry.
for camera in cameras:
    body = "Clear daylight on a dry straight suburban road, white dashed lane markings, low curbs and regularly spaced roadside poles."
    if camera.startswith("camera_front"):
        body += " A car ahead moves forward along the road and a parked car stands beside the right curb."
    elif camera.startswith("camera_cross_right"):
        body += " A parked car stands beside the right curb as the vehicle passes it."
    body += " The camera rig moves forward" + (
        " and smoothly shifts left." if args.variant == "lane_change" else " along its lane."
    )
    (captions / f"{camera}.json").write_text(
        json.dumps(
            {
                "caption_structured": {
                    f"chunk_0_{args.frames + 3}": {
                        "caption": body,
                        "start_frame": 0,
                        "end_frame": args.frames + 3,
                    }
                }
            },
            indent=2,
        )
        + "\n"
    )
manifest = dict(
    variant=args.variant,
    camera_frames=args.frames,
    camera_fps=30,
    pose_frames=len(time),
    cameras=cameras,
    vehicle_speed_x_m_s=4,
    lateral_displacement_m=float(y[-1]),
    lead_vehicle_speed_m_s=3,
    source="Explicit synthetic geometry and trajectories; no recorded sensor observations",
    camera_calibration_source=str(rig_path.relative_to(ROOT)),
    camera_rig_sha256=hashlib.sha256(rig_path.read_bytes()).hexdigest(),
    lidar_mount_source="Explicit synthetic mount [1.1,0,1.9] m FLU, not recorded calibration",
    coordinate_system="World fixed at initial rear axle ground projection; vehicle FLU; camera OpenCV",
    structural_validation=report,
)
(scene / "scene_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(scene, flush=True)
