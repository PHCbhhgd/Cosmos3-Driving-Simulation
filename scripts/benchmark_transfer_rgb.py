"""Measure Transfer RGB durations separately from joint sensor capacity tests."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--runtime", type=Path, required=True)
    p.add_argument("--python", type=Path, required=True)
    p.add_argument("--gpus", required=True)
    p.add_argument("--scene", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--wait-for-idle", action="store_true")
    args = p.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    args.scene = args.scene.resolve()
    runtime = args.runtime.resolve()
    env = os.environ | {"COSMOS3_GPUS": args.gpus}
    records = []
    for spec in json.loads((args.scene / "temporal_requests.json").read_text()):
        request = args.scene / spec["request"]
        payload = json.loads(request.read_text())
        name = payload["name"]

        def ready():
            return subprocess.run(
                ["python3", str(ROOT / "scripts/check_gpus.py"), "--gpus", args.gpus],
                capture_output=True,
                text=True,
            )

        checked = ready()
        while checked.returncode and args.wait_for_idle:
            print("WAIT allocated GPU group busy", flush=True)
            time.sleep(15)
            checked = ready()
        if checked.returncode:
            raise RuntimeError("Selected GPUs busy: no inference started")
        output = args.output / name
        output.mkdir()
        (output / "gpu_preflight.json").write_text(checked.stdout)
        started = time.monotonic()
        record = spec | dict(
            case=name, status="running", started_at=datetime.now(timezone.utc).isoformat()
        )
        (output / "run.json").write_text(json.dumps(record, indent=2) + "\n")
        print("START", name, flush=True)
        command = [
            "bash",
            str(runtime),
            str(args.python.absolute()),
            "-m",
            "torch.distributed.run",
            "--standalone",
            "--nproc-per-node=4",
            "-m",
            "cosmos_framework.scripts.inference",
            "-i",
            str(request),
            "-o",
            str(output / "raw"),
            "--checkpoint-path",
            str(ROOT / "storage/models/Cosmos3-Nano-Transfer-Auto"),
            "--resolution",
            "480",
            "--num-steps",
            "35",
            "--per-view-negative-prompt",
            (
                ROOT
                / "repos/cosmos-framework/.agents/skills/cosmos3-nano-transfer-auto/inference/assets/negative-prompt.txt"
            ).read_text(),
            "--cp-size",
            "4",
            "--cfgp-size",
            "1",
            "--dp-shard-size",
            "4",
            "--offload-guardrail-models",
            "--no-use-torch-compile",
            "--no-diffusion-cache",
        ]
        with (output / "inference.log").open("w") as handle:
            run = subprocess.run(
                command,
                env=env,
                cwd=ROOT / "repos/cosmos-framework",
                stdout=handle,
                stderr=subprocess.STDOUT,
            )
        record.update(
            inference_exit_code=run.returncode,
            sampling_and_decode_seconds=time.monotonic() - started,
        )
        sample = output / "raw" / name
        result = sample / "sample_outputs.json"
        result = json.loads(result.read_text()) if result.exists() else {}
        videos = sorted(sample.glob("vision_*.mp4"))
        if result.get("status") == "success" and len(videos) == 1:
            extra_frames = []
            if spec["chunks"] > 1:
                boundary = spec["chunk_frames"] - 1
                extra_frames = ["--extra-frames", *map(str, range(boundary - 3, boundary + 5))]
            with (output / "review.log").open("w") as handle:
                reviewed = subprocess.run(
                    [
                        "python3",
                        str(ROOT / "scripts/review_video.py"),
                        str(videos[0]),
                        "--output",
                        str(output / "review"),
                        "--interval",
                        "1",
                        "--expected-frames",
                        str(spec["expected_frames"]),
                        *extra_frames,
                    ],
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                )
            record.update(
                status="generated_and_decoded"
                if reviewed.returncode == 0
                else "generated_video_validation_failed",
                review_exit_code=reviewed.returncode,
            )
        else:
            log = (output / "inference.log").read_text(errors="replace")
            oom = "torch.OutOfMemoryError" in log or "CUDA out of memory" in log
            record.update(
                status="failed",
                failure_category="gpu_memory_capacity" if oom else "inference_or_output_failure",
            )
        record["total_seconds"] = time.monotonic() - started
        (output / "run.json").write_text(json.dumps(record, indent=2) + "\n")
        records.append(record)
        (args.output / "results.json").write_text(json.dumps(records, indent=2) + "\n")
        print("DONE", name, record["status"], record["total_seconds"], flush=True)


if __name__ == "__main__":
    main()
