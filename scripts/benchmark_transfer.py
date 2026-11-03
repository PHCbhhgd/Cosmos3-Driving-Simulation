"""Execute prepared Transfer-Auto cases and preserve every failure/recovery outcome."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runtime", type=Path, required=True, help="Environment wrapper executed before commands"
    )
    parser.add_argument(
        "--python", type=Path, required=True, help="Python in the compatible Auto environment"
    )
    parser.add_argument("--gpus", required=True)
    parser.add_argument(
        "--cases",
        nargs="+",
        default=[
            "clear_turn",
            "rain_turn",
            "snow_turn",
            "occluded_pedestrian",
            "adjacent_collision",
            "tunnel_entry",
            "contradictory_turn",
        ],
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wait-for-idle", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    runtime = args.runtime.resolve()
    python = args.python.absolute()
    env = os.environ | {"COSMOS3_GPUS": args.gpus, "COSMOS3_SAVE_JOINT_LATENTS": "1"}
    records = []

    def ready():
        return subprocess.run(
            ["python3", str(ROOT / "scripts/check_gpus.py"), "--gpus", args.gpus],
            capture_output=True,
            text=True,
        )

    def run(command, log, cwd=ROOT, custom_env=None):
        with log.open("w") as handle:
            return subprocess.run(
                ["bash", str(runtime), *map(str, command)],
                cwd=cwd,
                env=custom_env or env,
                stdout=handle,
                stderr=subprocess.STDOUT,
            ).returncode

    for case in args.cases:
        scene = ROOT / "storage/scenarios" / case
        request = scene / "request-joint-61.json"
        if not request.exists():
            raise FileNotFoundError(request)
        checked = ready()
        while checked.returncode and args.wait_for_idle:
            print("WAIT allocated GPU group busy", flush=True)
            time.sleep(30)
            checked = ready()
        if checked.returncode:
            raise RuntimeError("Selected GPUs are busy; no inference started")
        resultdir = output / case
        resultdir.mkdir()
        (resultdir / "gpu_preflight.json").write_text(checked.stdout)
        start = time.monotonic()
        record = dict(
            case=case, started_at=datetime.now(timezone.utc).isoformat(), status="running"
        )
        (resultdir / "run.json").write_text(json.dumps(record, indent=2) + "\n")
        print("START", case, record["started_at"], flush=True)
        command = [
            python,
            "-m",
            "torch.distributed.run",
            "--standalone",
            "--nproc-per-node=4",
            "-m",
            "cosmos_framework.scripts.inference",
            "-i",
            request,
            "-o",
            resultdir / "raw",
            "--checkpoint-path",
            ROOT / "storage/models/Cosmos3-Nano-Transfer-Auto",
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
        code = run(command, resultdir / "inference.log", ROOT / "repos/cosmos-framework")
        sample = resultdir / "raw" / json.loads(request.read_text())["name"]
        record.update(
            inference_exit_code=code, sampling_and_decode_seconds=time.monotonic() - start
        )
        complete = (sample / "sample_outputs.json").exists() and json.loads(
            (sample / "sample_outputs.json").read_text()
        ).get("status") == "success"
        if (
            not complete
            and (sample / "joint_latents.safetensors").exists()
            and (sample / "joint_latents_args.json").exists()
        ):
            record["recovery"] = (
                "Isolated official VAEs from complete saved joint latents; no resampling"
            )
            for _ in range(10):
                if ready().returncode == 0:
                    break
                time.sleep(3)
            if ready().returncode == 0:
                dc = run(
                    [python, ROOT / "scripts/decode_joint_latents.py", sample],
                    resultdir / "decode.log",
                    custom_env=env | {"COSMOS3_GPUS": args.gpus.split(",")[0]},
                )
                record["decode_exit_code"] = dc
                complete = dc == 0
        if complete:
            bundle = resultdir / "bundle"
            package = run(
                [
                    python,
                    ROOT / "scripts/package_simulation.py",
                    sample,
                    "--request",
                    request,
                    "--scene",
                    scene,
                    "--output",
                    bundle,
                ],
                resultdir / "package.log",
                custom_env=env | {"COSMOS3_GPUS": "-1"},
            )
            record["package_exit_code"] = package
            if package == 0:
                review = run(
                    [python, ROOT / "scripts/review_sensor_bundle.py", bundle],
                    resultdir / "review.log",
                    custom_env=env | {"COSMOS3_GPUS": "-1"},
                )
                evaluate = run(
                    [python, ROOT / "scripts/evaluate_joint_controls.py", bundle, "--scene", scene],
                    resultdir / "controls.log",
                    custom_env=env | {"COSMOS3_GPUS": "-1"},
                )
                browser = subprocess.run(
                    [
                        "python3",
                        str(ROOT / "scripts/check_replay_browser.py"),
                        str(bundle),
                        "--report",
                        str(resultdir / "browser.json"),
                    ],
                    env=os.environ | {"COSMOS3_BROWSER": "/usr/bin/google-chrome"},
                    stdout=(resultdir / "browser.log").open("w"),
                    stderr=subprocess.STDOUT,
                )
                record.update(
                    status="generated_and_packaged",
                    review_exit_code=review,
                    geometry_diagnostics_exit_code=evaluate,
                    browser_exit_code=browser.returncode,
                )
            else:
                record["status"] = "generated_package_failed"
        else:
            record["status"] = "failed_no_valid_sensor_bundle"
        record.update(
            total_seconds=time.monotonic() - start, output=str(resultdir.relative_to(ROOT))
        )
        (resultdir / "run.json").write_text(json.dumps(record, indent=2) + "\n")
        records.append(record)
        (output / "results.json").write_text(json.dumps(records, indent=2) + "\n")
        print("DONE", case, record["status"], record["total_seconds"], flush=True)


if __name__ == "__main__":
    main()
