"""Run the upstream WSM4 renderer sequentially, without a Ray cluster."""

import argparse
from pathlib import Path

from hydra import compose, initialize_config_dir
from cosmos_auto.wm.cli import _render_sample_hdmap_v4_impl
import cosmos_auto.wm

parser = argparse.ArgumentParser()
parser.add_argument("scene", type=Path)
parser.add_argument("--frames", type=int, default=121)
args = parser.parse_args()
scene = args.scene.resolve()
config = Path(cosmos_auto.wm.__file__).parent / "conf"
with initialize_config_dir(config_dir=str(config), version_base=None):
    cfg = compose(
        config_name="render",
        overrides=[
            f"input_root={scene}",
            f"output_root={scene}/camera_controls",
            "version=v4",
            "camera_spec=internal_7cam",
            "input_fps_spec.input_pose_fps=30",
            "resolution_spec=resize_1280x720",
            "output_frame_spec.target_render_fps=30",
            f"output_frame_spec.target_chunk_frame={args.frames}",
            "output_frame_spec.overlap_frame=0",
            "output_frame_spec.max_chunk=1",
        ],
    )
_render_sample_hdmap_v4_impl(scene.name, cfg)
