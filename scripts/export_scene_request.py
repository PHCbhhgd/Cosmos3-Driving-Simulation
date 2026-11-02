"""Validate rendered controls and export a native joint text-to-video request."""

import argparse
import json
import subprocess
from pathlib import Path
from request_window import shorten_request

import torch
from safetensors.torch import load_file

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("scene", type=Path)
parser.add_argument(
    "--frames", type=int, default=61, help="First 4k+1 frames; input controls remain unchanged"
)
args = parser.parse_args()
scene = args.scene.resolve()
manifest = json.loads((scene / "scene_manifest.json").read_text())
frames = manifest["camera_frames"]
views, checks = [], []
for camera in manifest["cameras"]:
    control = scene / "camera_controls/world_scenario" / f"ftheta_{camera}" / f"{scene.name}_0.mp4"
    metadata = json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-count_frames",
                "-show_entries",
                "stream=width,height,r_frame_rate,nb_read_frames",
                "-of",
                "json",
                str(control),
            ],
            text=True,
        )
    )["streams"][0]
    assert int(metadata["nb_read_frames"]) == frames, metadata
    assert metadata["r_frame_rate"] == "30/1", metadata
    assert (metadata["width"], metadata["height"]) == (1280, 720), metadata
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-xerror",
            "-i",
            str(control),
            "-f",
            "null",
            "-",
        ],
        check=True,
    )
    checks.append(dict(camera=camera, stream=metadata, full_decode=True))
    views.append(
        dict(
            camera_key=camera,
            control_path=str(control.relative_to(scene)),
            caption_path=f"captions/{camera}.json",
        )
    )
lidar = scene / f"lidar_controls/controls/{scene.name}/lidar_control.safetensors"
tensors = load_file(str(lidar))
assert set(tensors) == {"frames"}
tensor = tensors["frames"]
assert tensor.shape[0] == 3 and tuple(tensor.shape[2:]) == (128, 1800)
assert tensor.shape[1] >= round(frames / 3)
assert torch.isfinite(tensor).all()
request = dict(
    name=f"trajectory_{scene.name}",
    model_mode="text2video",
    resolution="480",
    aspect_ratio="16,9",
    fps=30,
    num_frames=frames,
    num_video_frames_per_chunk=frames,
    seed=0,
    num_outputs=1,
    guidance=3,
    control_guidance=1,
    shift=10,
    normalize_cfg=False,
    autoregressive=False,
    wsm={},
    lidar={"control_path": str(lidar.relative_to(scene))},
    prompt="",
    multiview=dict(
        load_caption_from_data=True,
        use_first_chunk_only=True,
        condition_video_as_image=False,
        optimize_raw_pixel_memory=True,
        views=views,
    ),
)
request = shorten_request(request, scene, args.frames)
request_path = scene / f"request-joint-{args.frames}.json"
request_path.write_text(json.dumps(request, indent=2) + "\n")
report = dict(
    status="passed",
    cameras=checks,
    lidar_control_shape=list(tensor.shape),
    lidar_valid_cells_per_sweep=(tensor[2] > 0.5).sum(dim=(1, 2)).tolist(),
    provenance="Synthetic scene geometry/trajectory controls, not model-generated sensor outputs",
)
(scene / "input_validation.json").write_text(json.dumps(report, indent=2) + "\n")
print(request_path, flush=True)
