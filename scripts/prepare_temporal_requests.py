"""Create front-camera RGB duration requests with actual 30 FPS controls.

The continuation uses 397 frames per chunk and one feedback frame. The second
control range begins at frame 396, so its first frame matches the previous tail.
No frames are slowed down or repeated to manufacture a longer video.
"""

import argparse
import json
from pathlib import Path


def chunk_ranges(frames, chunks=1, feedback=1):
    if frames < 1 or (frames - 1) % 4 or chunks < 1 or not 0 <= feedback < frames:
        raise ValueError("Require 4k+1 frames, positive chunks and feedback shorter than a chunk")
    return [(i * (frames - feedback), i * (frames - feedback) + frames + 3) for i in range(chunks)]


def prepare(scene, durations=((121, 1), (241, 1), (397, 1), (397, 2))):
    manifest = json.loads((scene / "scene_manifest.json").read_text())
    camera = "camera_front_wide_120fov"
    original = json.loads((scene / "captions" / f"{camera}.json").read_text())
    caption = next(iter(original["caption_structured"].values()))["caption"]
    control = f"camera_controls/world_scenario/ftheta_{camera}/{scene.name}_0.mp4"
    if not (scene / control).is_file():
        raise FileNotFoundError(control)
    requests = []
    for frames, chunks in durations:
        ranges = chunk_ranges(frames, chunks)
        if ranges[-1][1] > manifest["camera_frames"]:
            raise ValueError("Need controls covering every caption range, including alignment tail")
        total = frames * chunks - (chunks - 1)
        name = f"front-rgb-{total}"
        path = scene / f"captions-{name}.json"
        path.write_text(
            json.dumps(
                {
                    "caption_structured": {
                        f"chunk_{start}_{end}": {
                            "caption": caption,
                            "start_frame": start,
                            "end_frame": end,
                        }
                        for start, end in ranges
                    }
                },
                indent=2,
            )
            + "\n"
        )
        request = dict(
            name=name,
            model_mode="text2video",
            resolution="480",
            aspect_ratio="16,9",
            fps=30,
            num_frames=total,
            num_video_frames_per_chunk=frames,
            num_conditional_frames=1,
            seed=0,
            num_outputs=1,
            guidance=3,
            control_guidance=1,
            shift=10,
            normalize_cfg=False,
            autoregressive=False,
            wsm={},
            prompt="",
            multiview=dict(
                load_caption_from_data=True,
                use_first_chunk_only=chunks == 1,
                condition_video_as_image=False,
                optimize_raw_pixel_memory=True,
                views=[dict(camera_key=camera, control_path=control, caption_path=path.name)],
            ),
        )
        target = scene / f"request-{name}.json"
        target.write_text(json.dumps(request, indent=2) + "\n")
        requests.append(
            dict(
                request=target.name,
                expected_frames=total,
                chunks=chunks,
                chunk_frames=frames,
                caption_ranges=ranges,
                scope="One RGB view only; no LiDAR or seven-camera stability claim",
            )
        )
    (scene / "temporal_requests.json").write_text(json.dumps(requests, indent=2) + "\n")
    return requests


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("scene", type=Path)
    p.add_argument("--single-chunk-frames", type=int, help="Prepare only this single-chunk request")
    args = p.parse_args()
    durations = (
        ((args.single_chunk_frames, 1),)
        if args.single_chunk_frames is not None
        else ((121, 1), (241, 1), (397, 1), (397, 2))
    )
    print(json.dumps(prepare(args.scene, durations), indent=2))


if __name__ == "__main__":
    main()
