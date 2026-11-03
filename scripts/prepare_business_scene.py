"""Build synthetic driving stress scenes using explicit geometry and actor trajectories."""

import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
WSM = ROOT / "repos/cosmos-framework/.agents/skills/cookbooks/cosmos3/simulation/auto/wsm"
CAMERAS = [
    "camera_front_wide_120fov",
    "camera_cross_left_120fov",
    "camera_cross_right_120fov",
    "camera_rear_left_70fov",
    "camera_rear_right_70fov",
    "camera_rear_tele_30fov",
    "camera_front_tele_30fov",
]


def pose(x, y, z=0, yaw=0):
    a = np.eye(4)
    a[:3, 3] = [x, y, z]
    a[:2, :2] = [[np.cos(yaw), -np.sin(yaw)], [np.sin(yaw), np.cos(yaw)]]
    return a


def centerline(s, offset=0, curved=False):
    s = np.asarray(s)
    if not curved:
        return np.stack([s, np.full_like(s, offset), np.zeros_like(s)], axis=-1)
    radius = 22.0
    theta = np.clip(s / radius, -0.6, np.pi / 2)
    # Continue tangentially beyond the quarter turn; avoid a circular road loop.
    base = np.stack(
        [radius * np.sin(theta), radius * (1 - np.cos(theta)), np.zeros_like(theta)], axis=-1
    )
    remainder = s - radius * theta
    base += np.stack(
        [remainder * np.cos(theta), remainder * np.sin(theta), np.zeros_like(theta)], axis=-1
    )
    base += np.stack(
        [-offset * np.sin(theta), offset * np.cos(theta), np.zeros_like(theta)], axis=-1
    )
    return base


def map_end_for_frames(frames):
    # Keep at least 120 m of road ahead even at the final alignment-tail pose.
    return max(180, int(np.ceil(6 * (frames + 2) / 30)) + 120)


def scenario_state(geometry, times, lead_speed=3):
    if not np.isfinite(lead_speed) or lead_speed < 0:
        raise ValueError("lead_speed must be finite and nonnegative")
    curved = geometry == "left_turn"
    speed = 6 if curved else 4
    positions = centerline(speed * times, curved=curved)
    yaw = np.clip(speed * times / 22, -0.6, np.pi / 2) if curved else np.zeros_like(times)
    ego = np.array([pose(*p, yaw=a) for p, a in zip(positions, yaw)])
    objects = []
    lead_poses = []
    for t in times:
        frame = {}

        def actor(key, kind, lwh, x, y, z, yaw=0, moving=False):
            p = pose(x, y, z, yaw)
            frame[key] = dict(
                object_type=kind,
                object_is_moving=moving,
                object_lwh=lwh,
                object_to_world=p.tolist(),
            )
            return p

        lp = centerline(np.array(24 + lead_speed * t), curved=curved)
        lyaw = min((24 + lead_speed * t) / 22, np.pi / 2) if curved else 0
        lead = actor("lead_car", "Car", [4.5, 1.8, 1.6], lp[0], lp[1], 0.8, lyaw, True)
        if geometry == "occluded_pedestrian":
            actor("occluding_van", "Truck", [5.8, 2.3, 2.8], 13, -3.5, 1.4)
            # Person starts behind the van on its far side, emerges around its front.
            progress = np.clip((t - 0.4) / 1.2, 0, 1)
            py = -5.0 + 6.0 * (progress * progress * (3 - 2 * progress))
            actor(
                "crossing_person", "Pedestrian", [0.65, 0.65, 1.75], 14, py, 0.875, np.pi / 2, True
            )
        elif geometry == "adjacent_collision":
            actor("stopped_adjacent_car", "Car", [4.5, 1.8, 1.6], 17, 3.5, 0.8)
            before = min(t, 1.1)
            after = max(0, t - 1.1)
            actor(
                "impacting_car",
                "Car",
                [4.5, 1.8, 1.6],
                7 + 5 * before,
                3.5 + 0.25 * after,
                0.8,
                min(after * 0.7, 0.45),
                True,
            )
        elif geometry not in ["left_turn", "tunnel_entry"]:
            actor("parked_car", "Car", [4.5, 1.8, 1.6], 12, -4.3, 0.8)
        objects.append(frame)
        lead_poses.append(lead)
    return ego, np.array(lead_poses), objects


def caption_for(case, camera):
    weather = case["weather"]
    geo = case["geometry"]
    front = camera.startswith("camera_front")
    right = camera == "camera_cross_right_120fov"
    if weather == "heavy_rain":
        body = "Heavy rain in overcast daylight. Visible falling rain, wet dark asphalt, puddles, tire spray and reflections. Reduced visibility, consistent rainy weather across all views."
    elif weather == "snow":
        body = "Winter daytime with steady visible snowfall, overcast sky, accumulated white snow along the curbs and slushy wheel tracks on the road. Snowy trees and reduced visibility, consistent winter weather across all views."
    elif weather == "tunnel":
        body = (
            "A paved urban road enters a concrete tunnel. The vehicle approaches the dark tunnel portal in daylight, enters beneath a continuous concrete roof, then moves between concrete side walls under regularly spaced warm overhead lamps. Exposure gradually adjusts from bright daylight to the dim tunnel interior."
            if front
            else "The camera is on a vehicle entering a concrete tunnel. Concrete side walls and a roof approach and enclose the view as daylight gives way to dim warm tunnel illumination. Rear-facing views initially see the bright outdoor road behind."
        )
    else:
        body = "Clear daylight on a dry paved road, white dashed lane markings, low curbs and regularly spaced roadside poles."
    if geo == "left_turn":
        body += " The road curves left and the camera rig follows a smooth left turn."
        if front:
            body += " A car farther ahead follows the same left curve. Lane geometry and roadside objects move smoothly with the turning perspective."
        if weather == "contradictory":
            body = "Clear dry daylight. The road turns sharply RIGHT and the camera rig steers RIGHT. All lane markings curve RIGHT. A car ahead turns RIGHT. No left turn."
    elif geo == "occluded_pedestrian":
        if front or right:
            body += " A tall van is parked on the right. A pedestrian initially hidden behind the van suddenly emerges near its front and moves from the right curb toward the left across the road. The same pedestrian remains present and keeps a consistent appearance."
        else:
            body += " The rig moves forward on the same road; a parked van and crossing pedestrian appear only if inside this camera view."
    elif geo == "adjacent_collision":
        if front or camera == "camera_cross_left_120fov":
            body += " In the adjacent lane to the left, a moving car approaches a stopped car and bumps its rear around the middle of the shot. The moving car abruptly slows and rotates slightly after contact. Both vehicles remain visible and keep their identities. No injured people, no gore."
        else:
            body += " The rig moves forward beside two cars making contact in the adjacent left lane; show the event only if visible from this camera."
    return body


def build(case, frames, output):
    assert frames >= 61 and (frames - 1) % 4 == 0
    scene = output.resolve()
    assert not scene.exists(), f"Preserve scene {scene}"
    spec = importlib.util.spec_from_file_location(
        "rds_hq_io", WSM / "skills/scenario-to-rds-hq/scripts/rds_hq_io.py"
    )
    io = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(io)
    rig_path = WSM / "skills/scenario-to-rds-hq/assets/hyperion8.json"
    rig = json.loads(rig_path.read_text())
    times = np.arange(frames + 3, dtype=float) / 30
    ego, lead, objects = scenario_state(case["geometry"], times, case.get("lead_speed_mps", 3))
    layers = {k: {"labels": []} for k in io.MAP_GEOMETRY}

    def line(layer, vertices, attributes=None):
        layers[layer]["labels"].append(
            {
                "labelData": {
                    "shape3d": {
                        "polyline3d": {"vertices": np.asarray(vertices).tolist()},
                        "attributes": attributes or [],
                    }
                }
            }
        )

    map_end = map_end_for_frames(frames)
    s = np.arange(-30, map_end + 1, dtype=float)
    curved = case["geometry"] == "left_turn"
    for y in [-5.5, 5.5]:
        line(
            "3d_road_boundaries",
            centerline(s, y, curved),
            [{"name": "boundary_type", "text": "curb"}],
        )
    for y in [-1.75, 1.75]:
        line(
            "3d_lanelines",
            centerline(s, y, curved),
            [
                {"name": "colors", "enumsList": {"enumsList": ["WHITE"]}},
                {"name": "styles", "enumsList": {"enumsList": ["LONG_DASHED_SINGLE"]}},
            ],
        )
    pole_distances = [5, 20, 35, 50, 65, 80, 100, 130, 160]
    pole_distances.extend(range(190, map_end + 1, 15))
    for dist in pole_distances:
        for side in [-5.5, 5.5]:
            p = centerline(np.array(float(dist)), side, curved)
            line("3d_poles", [p, p + [0, 0, 5]])
    if case["geometry"] == "tunnel_entry":
        # Wireframe structural anchors only; no fake dense tunnel mesh is claimed.
        for x in range(4, 100, 4):
            line("3d_poles", [[x, -5.5, 0], [x, -5.5, 5], [x, 5.5, 5], [x, 5.5, 0]])
        line("3d_poles", [[4, -5.5, 5], [100, -5.5, 5]])
        line("3d_poles", [[4, 5.5, 5], [100, 5.5, 5]])
    report = io.write_clip(
        scene,
        scene.name,
        {c: ego @ np.asarray(rig[c]["camera_to_vehicle"]) for c in CAMERAS},
        {c: np.asarray(rig[c]["ftheta_intrinsics"]) for c in CAMERAS},
        objects,
        layers,
        {"state_to_legacy_render_state": {}, "traffic_light_states": {}},
        camera_type="ftheta",
    )
    io.write_archive(
        scene / "vehicle_pose" / f"{scene.name}.tar",
        scene.name,
        {f"{i:06d}.vehicle_pose.npy": p for i, p in enumerate(ego)},
    )
    (scene / "rig").mkdir()
    (scene / "rig" / f"{scene.name}.json").write_text(
        json.dumps(
            {
                "rig": {
                    "sensors": [
                        {
                            "name": "lidar:gt:top:p128",
                            "nominalSensor2Rig_FLU": {
                                "roll-pitch-yaw": [0, 0, 0],
                                "t": [1.1, 0, 1.9],
                            },
                        }
                    ]
                }
            },
            indent=2,
        )
        + "\n"
    )
    mount = pose(1.1, 0, 1.9)
    np.savez_compressed(
        scene / "trajectory.npz",
        timestamps_s=times,
        vehicle_to_world=ego,
        lead_car_to_world=lead,
        lidar_to_vehicle=mount,
    )
    with (scene / "trajectory.csv").open("w") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["frame_id", "timestamp_s", "ego_x_m", "ego_y_m", "ego_yaw_rad", "lead_car_x_m"]
        )
        for i, t in enumerate(times):
            writer.writerow(
                [i, t, *ego[i, :2, 3], np.arctan2(ego[i, 1, 0], ego[i, 0, 0]), lead[i, 0, 3]]
            )
    (scene / "captions").mkdir()
    for c in CAMERAS:
        (scene / "captions" / f"{c}.json").write_text(
            json.dumps(
                {
                    "caption_structured": {
                        f"chunk_0_{frames + 3}": {
                            "caption": caption_for(case, c),
                            "start_frame": 0,
                            "end_frame": frames + 3,
                        }
                    }
                },
                indent=2,
            )
            + "\n"
        )
    manifest = dict(
        variant=case["id"],
        camera_frames=frames,
        camera_fps=30,
        pose_frames=len(times),
        cameras=CAMERAS,
        source="Programmatically specified synthetic business scenario, not recorded observations",
        camera_calibration_source=str(rig_path.relative_to(ROOT)),
        camera_rig_sha256=hashlib.sha256(rig_path.read_bytes()).hexdigest(),
        lidar_mount_source="Synthetic [1.1,0,1.9] m FLU",
        coordinate_system="World initial rear axle; vehicle FLU; camera OpenCV",
        road_arc_length_extent_m=[-30, map_end],
        benchmark_case=case,
        structural_validation=report,
    )
    (scene / "scene_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (scene / "actors.json").write_text(
        json.dumps({"timestamps_s": times.tolist(), "frames": objects}, indent=2) + "\n"
    )
    print(scene, flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("case")
    p.add_argument("--frames", type=int, default=61)
    p.add_argument("--output", type=Path)
    p.add_argument("--lead-speed", type=float, help="Override lead speed in m/s; default 3")
    args = p.parse_args()
    cases = json.loads((ROOT / "configs/robustness-cases.json").read_text())["cases"]
    case = next(c for c in cases if c["id"] == args.case)
    if args.lead_speed is not None:
        case = case | {"lead_speed_mps": args.lead_speed}
    build(case, args.frames, args.output or ROOT / "storage/scenarios" / case["id"])


if __name__ == "__main__":
    main()
