"""Run a seeded reduced Nano T2V check with default safety checks enabled."""

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import torch
from cosmos3_streaming import StreamingConfig, build_pipeline
from diffusers.utils import export_to_video

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--frames", type=int, default=17)
parser.add_argument("--steps", type=int, default=4)
parser.add_argument("--height", type=int, default=240)
parser.add_argument("--width", type=int, default=432)
parser.add_argument("--seed", type=int, default=0)
args = parser.parse_args()
stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
out = ROOT / "outputs" / f"nano-smoke-{stamp}"
out.mkdir(parents=True)
settings = vars(args) | {
    "model": "nvidia/Cosmos3-Nano",
    "revision": json.loads((ROOT / "configs/versions.json").read_text())["models"]["Cosmos3-Nano"][
        "revision"
    ],
    "prompt": '{"scene":"A stationary camera observes a quiet suburban road in daylight. A blue car moves slowly along its lane. Trees and buildings remain stable in the background."}',
    "fps": 24,
    "guidance_scale": 6.0,
    "safety_checker": True,
    "purpose": "Reduced smoke check; not an official quality benchmark",
}
(out / "request.json").write_text(json.dumps(settings, indent=2))
print(f"Output directory: {out}", flush=True)
start = time.perf_counter()
report = {"status": "running", "settings": settings}
try:
    pipe = build_pipeline(
        str(ROOT / "storage/models/Cosmos3-Nano"),
        config=StreamingConfig(device="cuda:0"),
        dtype=torch.bfloat16,
        local_files_only=True,
    )
    assert pipe.requires_safety_checker and pipe.safety_checker is not None
    print("Pipeline loaded; starting seeded generation", flush=True)
    report["load_seconds"] = time.perf_counter() - start
    frames = pipe(
        prompt=settings["prompt"],
        negative_prompt="",
        num_frames=args.frames,
        height=args.height,
        width=args.width,
        num_inference_steps=args.steps,
        guidance_scale=settings["guidance_scale"],
        fps=settings["fps"],
        generator=torch.Generator(device="cuda:0").manual_seed(args.seed),
        output="videos",
    )
    path = out / "video.mp4"
    export_to_video(frames, str(path), fps=settings["fps"])
    report.update(
        status="generated",
        elapsed_seconds=time.perf_counter() - start,
        video_sha256=hashlib.file_digest(path.open("rb"), "sha256").hexdigest(),
        peak_gpu_allocated_bytes=torch.cuda.max_memory_allocated(),
    )
except Exception as exc:
    report.update(
        status="failed",
        error_type=type(exc).__name__,
        error=str(exc),
        elapsed_seconds=time.perf_counter() - start,
    )
    raise
finally:
    (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)
