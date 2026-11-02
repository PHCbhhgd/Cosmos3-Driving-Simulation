"""Download complete immutable model snapshots using normal HF authentication."""

import argparse
import json
from pathlib import Path
from huggingface_hub import snapshot_download

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("target", choices=["nano", "sample", "transfer", "sim"])
args = parser.parse_args()
name = {
    "nano": "Cosmos3-Nano",
    "sample": "Cosmos3-Nano-Transfer-Auto",
    "transfer": "Cosmos3-Nano-Transfer-Auto",
    "sim": "Cosmos3-Nano-Sim-Auto",
}[args.target]
config = json.loads((ROOT / "configs/versions.json").read_text())["models"][name]
dest = ROOT / "storage" / ("auto_sample" if args.target == "sample" else f"models/{name}")
snapshot_download(
    repo_id=config["repo_id"],
    revision=config["revision"],
    allow_patterns=["assets/sample_data/**"] if args.target == "sample" else None,
    local_dir=dest,
    token=True,
    max_workers=4,
)
print(f"Completed {config['repo_id']}@{config['revision']} -> {dest}")
