"""Count generated LiDAR points near prescribed actor boxes, without semantic claims.

This diagnostic uses a sweep-start pose and therefore does not deskew a spinning
scan. A nearby road, wall or other actor can create false support. Counts are not
object detection accuracy or collision-physics validation.
"""

import argparse
import json
from pathlib import Path

import numpy as np


def read_points(path):
    with path.open("rb") as handle:
        for _ in range(100):
            line = handle.readline()
            if line == b"end_header\n":
                return np.frombuffer(handle.read(), dtype="<f4").reshape(-1, 4)[:, :3]
            if not line:
                break
    raise ValueError(f"Invalid PLY header: {path.name}")


def near_box(points_world, actor, tolerance=0.35):
    transform = np.asarray(actor["object_to_world"])
    local = (points_world - transform[:3, 3]) @ transform[:3, :3]
    half = np.asarray(actor["object_lwh"]) / 2
    inside_expanded = np.all(np.abs(local) <= half + tolerance, axis=1)
    surface_distance = np.abs(np.abs(local) - half).min(axis=1)
    return inside_expanded & (surface_distance <= tolerance)


def evaluate(bundle, scene):
    manifest = json.loads((bundle / "bundle_manifest.json").read_text())
    actors = json.loads((scene / "actors.json").read_text())["frames"]
    trajectory = np.load(scene / "trajectory.npz")
    records = []
    for sweep in manifest["sweeps"]:
        index = sweep["frame_id"]
        points = read_points(bundle / sweep["file"])
        sensor_to_world = trajectory["vehicle_to_world"][index] @ trajectory["lidar_to_vehicle"]
        world = points @ sensor_to_world[:3, :3].T + sensor_to_world[:3, 3]
        counts = {key: int(near_box(world, actor).sum()) for key, actor in actors[index].items()}
        records.append(
            dict(
                frame_id=index,
                timestamp_s=sweep["timestamp_s"],
                generated_points=len(points),
                points_near_actor_box=counts,
            )
        )
    report = dict(tolerance_m=0.35, scope=__doc__.strip(), sweeps=records)
    output = bundle / "review/actor_support.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("bundle", type=Path)
    p.add_argument("--scene", type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(evaluate(args.bundle, args.scene), indent=2))


if __name__ == "__main__":
    main()
