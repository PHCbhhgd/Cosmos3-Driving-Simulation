"""Run the upstream WSM4 renderer sequentially, without a Ray cluster."""

import argparse
from pathlib import Path

from hydra import compose, initialize_config_dir
from cosmos_auto.wm.cli import _render_sample_hdmap_v4_impl
import cosmos_auto.wm

parser = argparse.ArgumentParser()
parser.add_argument("scene", type=Path)
parser.add_argument("--frames", type=int, default=121)
parser.add_argument("--front-only", action="store_true", help="Render only front-wide controls")
parser.add_argument(
    "--egl-device", type=int, help="Physical EGL device index; CUDA visibility is separate"
)
args = parser.parse_args()
if args.egl_device is not None:
    if args.egl_device < 0:
        parser.error("--egl-device must be nonnegative")
    import moderngl

    original_create_context = moderngl.create_context

    def create_context_on_selected_device(*context_args, **settings):
        # Upstream non-Ray rendering always selects EGL 0, ignoring CUDA visibility.
        # Scope this adapter to this renderer process so shared-server jobs can
        # select their allocated physical GPU without modifying installed packages.
        settings["device_index"] = args.egl_device
        context = original_create_context(*context_args, **settings)
        print(f"EGL device {args.egl_device}: {context.info['GL_RENDERER']}", flush=True)
        return context

    moderngl.create_context = create_context_on_selected_device
scene = args.scene.resolve()
config = Path(cosmos_auto.wm.__file__).parent / "conf"
with initialize_config_dir(config_dir=str(config), version_base=None):
    cfg = compose(
        config_name="render",
        overrides=[
            f"input_root={scene}",
            f"output_root={scene}/camera_controls",
            "version=v4",
            f"camera_spec={'internal_1cam' if args.front_only else 'internal_7cam'}",
            "input_fps_spec.input_pose_fps=30",
            "resolution_spec=resize_1280x720",
            "output_frame_spec.target_render_fps=30",
            f"output_frame_spec.target_chunk_frame={args.frames}",
            "output_frame_spec.overlap_frame=0",
            "output_frame_spec.max_chunk=1",
        ],
    )
_render_sample_hdmap_v4_impl(scene.name, cfg)
