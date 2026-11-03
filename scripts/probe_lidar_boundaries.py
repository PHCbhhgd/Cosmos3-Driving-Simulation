"""Probe official LiDAR range/validity boundaries on synthetic arrays, without sampling."""

# ruff: noqa: E402 -- import the pinned local Framework.
import argparse
import json
from pathlib import Path
import sys
import tempfile

import torch
from safetensors.torch import load_file

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "repos/cosmos-framework"))
from cosmos_framework.inference.lidar_transfer import save_lidar_range_view
from cosmos_framework.model.generator.tokenizers.lidar.normalization import metric_lidar_to_network
from cosmos_framework.model.generator.tokenizers.lidar.range_projection import (
    LidarRangeProjectionConfig,
)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    configurations = {}
    for name in ["Cosmos3-Nano-Transfer-Auto", "Cosmos3-Nano-Sim-Auto"]:
        config = json.loads((ROOT / "storage/models" / name / "config.json").read_text())
        configurations[name] = config["model"]["config"]["lidar_tokenizer"]["range_projection"]
    projection_config = dict(configurations["Cosmos3-Nano-Transfer-Auto"])
    projection_config.pop("_target", None)
    projection = LidarRangeProjectionConfig.from_dict(projection_config)
    values = [0.0, 2.0, 4.99, 5.0, 5.01, 20.0, 99.99, 100.0, 100.01, 120.0]
    values += [20.0, 20.0, 20.0]
    probabilities = [1.0] * 10 + [0.49, 0.5, 0.51]
    tensor = torch.ones(1, 3, len(values), 128, 1808)
    tensor[:, 0] = torch.tensor(values)[None, :, None, None]
    tensor[:, 1] = 0.5
    tensor[:, 2] = torch.tensor(probabilities)[None, :, None, None]
    _, valid = metric_lidar_to_network(
        tensor, min_range=projection.min_range_m, max_range=projection.max_range_m
    )
    with tempfile.TemporaryDirectory() as temporary:
        output = Path(temporary) / "synthetic-boundaries.safetensors"
        save_lidar_range_view(
            tensor, output, range_projection=projection, frame_ids=torch.arange(len(values)) * 3
        )
        saved = load_file(str(output))["range_m"]
    results = [
        dict(
            input_range_m=value,
            input_validity=probabilities[i],
            encoded_valid_fraction=float(valid[0, 0, i].float().mean()),
            saved_nonzero_fraction=float((saved[i] > 0).float().mean()),
            saved_range_min_m=float(saved[i].min()),
            saved_range_max_m=float(saved[i].max()),
        )
        for i, value in enumerate(values)
    ]
    report = dict(
        method="Unmodified official metric_lidar_to_network and save_lidar_range_view "
        "on constant synthetic arrays; no denoiser, learned VAE or Sim attention executed",
        configurations=configurations,
        results=results,
        scope="Representation and serialization boundary only; not generated sensor quality",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
