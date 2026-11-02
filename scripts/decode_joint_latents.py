"""Decode saved joint latents with isolated official VAEs, without loading the denoiser."""

# ruff: noqa: E402 -- use the pinned Framework checkout.
import argparse
import gc
import json
import sys
from pathlib import Path

import torch
from safetensors.torch import load_file
from huggingface_hub import hf_hub_download

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "repos/cosmos-framework"))
from cosmos_framework.inference.args import OmniSampleArgs
from cosmos_framework.inference.inference import OmniInference
from cosmos_framework.inference.lidar_transfer import save_lidar_range_view
from cosmos_framework.model.generator.tokenizers.lidar.lidar_tokenizer_v1 import (
    LidarTokenizerV1Interface,
)
from cosmos_framework.model.generator.tokenizers.lidar.range_projection import (
    LidarRangeProjectionConfig,
)
from cosmos_framework.model.generator.tokenizers.wan2pt2_vae_4x16x16 import (
    Wan2pt2VAEInterface,
)
from cosmos_framework.utils.generator.multiview import decode_multiview_latent_per_view

CHECKPOINT = ROOT / "storage/models/Cosmos3-Nano-Transfer-Auto"
CONFIG = json.loads((CHECKPOINT / "config.json").read_text())["model"]["config"]


def lidar_vae():
    cfg = dict(CONFIG["lidar_tokenizer"])
    cfg.pop("_target")
    cfg["vae_path"] = str(CHECKPOINT / "lidar_vae/diffusion_pytorch_model.safetensors")
    cfg["bucket_name"] = ""
    projection = dict(cfg["range_projection"])
    projection.pop("_target", None)
    cfg["range_projection"] = LidarRangeProjectionConfig.from_dict(projection)
    return LidarTokenizerV1Interface(**cfg)


def camera_vae():
    cfg = dict(CONFIG["tokenizer"])
    cfg.pop("_target")
    cfg["bucket_name"] = ""
    asset = json.loads((ROOT / "configs/versions.json").read_text())["wan_vae"]
    cfg["vae_path"] = hf_hub_download(
        asset["repo_id"], asset["file"], revision=asset["revision"], local_files_only=True
    )
    return Wan2pt2VAEInterface(**cfg)


def release():
    gc.collect()
    torch.cuda.empty_cache()


@torch.inference_mode()
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("sample", type=Path, nargs="?")
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    if args.preflight:
        torch.cuda.reset_peak_memory_stats()
        vae = lidar_vae()
        controls = load_file(
            str(
                ROOT
                / "storage/scenarios/lane_change/lidar_controls/controls/lane_change/lidar_control.safetensors"
            )
        )["frames"][:, :20]
        controls = torch.cat((controls[..., -4:], controls, controls[..., :4]), dim=-1)
        encoded = vae.encode(controls.unsqueeze(0))
        decoded = vae.decode(encoded)
        assert decoded.shape == (1, 3, 20, 128, 1808) and torch.isfinite(decoded).all()
        lidar_peak = torch.cuda.max_memory_allocated()
        del vae, controls, encoded, decoded
        release()
        torch.cuda.reset_peak_memory_stats()
        vae = camera_vae()
        test = vae.decode(torch.zeros(1, CONFIG["state_ch"], 16, 30, 52, device="cuda"))
        assert test.shape == (1, 3, 61, 480, 832) and torch.isfinite(test).all()
        report = dict(
            status="passed",
            scope="Isolated official VAE allocation/shape check on control reconstruction and zero camera latents; not generated sensor results",
            lidar_peak_allocated_bytes=lidar_peak,
            camera_peak_allocated_bytes=torch.cuda.max_memory_allocated(),
            lidar_streaming_chunk_frames=20,
            lidar_streaming_context_frames=21,
        )
        (ROOT / "artifacts").mkdir(exist_ok=True)
        (ROOT / "artifacts/isolated_vae_preflight.json").write_text(
            json.dumps(report, indent=2) + "\n"
        )
        print(json.dumps(report, indent=2), flush=True)
        return
    assert args.sample is not None
    sample = args.sample.resolve()
    params = OmniSampleArgs.model_validate_json((sample / "joint_latents_args.json").read_text())
    params.output_dir = sample
    tensors = load_file(str(sample / "joint_latents.safetensors"))
    vae = camera_vae()
    latent = tensors["vision"].cuda()
    if latent.ndim == 4:
        latent = latent.unsqueeze(0)
    video = decode_multiview_latent_per_view(
        lambda z: vae.decode(z).clamp(-1, 1),
        latent,
        len(params.multiview.views),
        params.num_frames,
        assemble_on_cpu=True,
    ).cpu()
    del latent, vae
    release()
    files, by_camera = OmniInference._save_multiview_view_videos(
        None,
        params,
        list(
            torch.chunk(
                ((1 + video.squeeze(0)) / 2).clamp(0, 1),
                len(params.multiview.views),
                dim=1,
            )
        ),
        prefix="vision",
        fps=int(params.fps),
    )
    del video
    vae = lidar_vae()
    latent = tensors["lidar"].cuda()
    if latent.ndim == 4:
        latent = latent.unsqueeze(0)
    decoded = vae.decode(latent).cpu()
    lidar_file = save_lidar_range_view(
        decoded,
        sample / "lidar.safetensors",
        range_projection=vae.range_projection,
        frame_ids=tensors["frame_ids"],
    )
    files.append(lidar_file)
    (sample / "sample_args.json").write_text(params.model_dump_json())
    result = dict(
        args=params.model_dump(mode="json"),
        status="success",
        outputs=[
            dict(
                content=dict(
                    files_by_camera=by_camera,
                    lidar=str(lidar_file),
                    fps=params.fps,
                    lidar_fps=CONFIG["lidar_fps"],
                    decode_provenance="Official unchanged VAE weights/configuration; isolated postprocess from persisted joint latents, no re-sampling",
                ),
                files=[str(f) for f in files],
            )
        ],
    )
    (sample / "sample_outputs.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"Decoded saved joint sample: {sample}", flush=True)


if __name__ == "__main__":
    main()
