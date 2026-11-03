"""Run actual Nano temporal stress tests; record each independent generation."""

import argparse
import hashlib
import json
from pathlib import Path
import time

import torch
from cosmos3_streaming import StreamingConfig, build_pipeline
from diffusers.utils import export_to_video

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frames", type=int, nargs="+", default=[121, 241, 397])
    parser.add_argument(
        "--cases-config", type=Path, help="Optional list of id/prompt/frames/seed cases"
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    settings = dict(
        model="Cosmos3-Nano",
        steps=35,
        seed=0,
        width=848,
        height=480,
        fps=24,
        guidance=6,
        safety_checker=True,
        prompt='{"scene":"A fixed stationary roadside camera observes the same suburban road in clear daylight. A single blue sedan drives slowly straight ahead away from the camera. The road, lane markings, houses, lamp posts and trees stay fixed in world coordinates. Continuous uninterrupted shot, no cuts, no zoom."}',
    )
    (args.output / "settings.json").write_text(json.dumps(settings, indent=2) + "\n")
    cases = (
        json.loads(args.cases_config.read_text())
        if args.cases_config
        else [
            dict(id=f"frames-{f}", frames=f, prompt=settings["prompt"], seed=0) for f in args.frames
        ]
    )
    (args.output / "cases.json").write_text(json.dumps(cases, indent=2) + "\n")
    pipe = build_pipeline(
        str(ROOT / "storage/models/Cosmos3-Nano"),
        config=StreamingConfig(device="cuda:0"),
        dtype=torch.bfloat16,
        local_files_only=True,
    )
    assert pipe.requires_safety_checker and pipe.safety_checker is not None
    reports = []
    for spec in cases:
        frames = spec["frames"]
        case = args.output / spec["id"]
        case.mkdir()
        started = time.monotonic()
        torch.cuda.reset_peak_memory_stats()
        report = (
            settings
            | spec
            | dict(
                frames=frames,
                status="running",
                scope="Independent T2V duration stress, not a continuation of shorter output; no geometry controls or physical GT.",
            )
        )
        print("START", frames, flush=True)
        try:
            videos = pipe(
                prompt=spec["prompt"],
                negative_prompt="",
                num_frames=frames,
                height=480,
                width=848,
                num_inference_steps=35,
                guidance_scale=6,
                fps=24,
                generator=torch.Generator(device="cuda:0").manual_seed(spec.get("seed", 0)),
                output="videos",
            )
            path = case / "video.mp4"
            export_to_video(videos, str(path), fps=24)
            with path.open("rb") as handle:
                sha = hashlib.file_digest(handle, "sha256").hexdigest()
            report.update(status="generated", video_sha256=sha)
            del videos
        except Exception as exc:
            report.update(status="failed", error_type=type(exc).__name__, error=str(exc))
            torch.cuda.empty_cache()
        report.update(
            elapsed_seconds=time.monotonic() - started,
            peak_gpu_allocated_bytes=torch.cuda.max_memory_allocated(),
        )
        (case / "result.json").write_text(json.dumps(report, indent=2) + "\n")
        reports.append(report)
        (args.output / "results.json").write_text(json.dumps(reports, indent=2) + "\n")
        print("DONE", frames, report["status"], report["elapsed_seconds"], flush=True)


if __name__ == "__main__":
    main()
