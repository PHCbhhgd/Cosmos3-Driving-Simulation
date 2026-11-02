"""Prefetch pinned Framework dependencies; honor HF_HOME, HF_TOKEN_PATH and HF_ENDPOINT."""

import json
from pathlib import Path
from huggingface_hub import snapshot_download, hf_hub_download

ROOT = Path(__file__).resolve().parents[1]
versions = json.loads((ROOT / "configs/versions.json").read_text())
for config in versions["dependencies"].values():
    snapshot_download(config["repo_id"], revision=config["revision"], token=True, max_workers=2)
config = versions["wan_vae"]
hf_hub_download(config["repo_id"], config["file"], revision=config["revision"], token=True)
print("Pinned safety models and Wan VAE downloaded to the configured Hugging Face cache.")
