"""Measure generated LiDAR agreement on explicitly controlled rays; report without a pass claim."""

# ruff: noqa: E402 -- pinned local projection helpers.
import argparse
import hashlib
import json
from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from safetensors.numpy import load_file

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "repos/cosmos-framework"))
from cosmos_framework.model.generator.tokenizers.lidar.geometry import range_map_to_xyz
from cosmos_framework.model.generator.tokenizers.lidar.range_projection import (
    LidarRangeProjectionConfig,
)

parser = argparse.ArgumentParser()
parser.add_argument("bundle", type=Path)
parser.add_argument("--scene", type=Path, required=True)
args = parser.parse_args()
bundle, scene = args.bundle.resolve(), args.scene.resolve()
manifest = json.loads((bundle / "bundle_manifest.json").read_text())
generated = load_file(str(bundle / "lidar.safetensors"))
control = load_file(str(scene / f"lidar_controls/controls/{scene.name}/lidar_control.safetensors"))[
    "frames"
]
projection = LidarRangeProjectionConfig.from_dict(manifest["range_projection"])
out = bundle / "review"
out.mkdir(exist_ok=True)
records = []
for sweep, frame in enumerate(generated["frame_ids"]):
    ctrl = control[:, int(frame) // 3]
    valid = ctrl[2] > 0.5
    predicted = generated["range_m"][sweep]
    matched = valid & (predicted > 0)
    error = np.abs(predicted[matched] - ctrl[0][matched])
    records.append(
        dict(
            frame_id=int(frame),
            timestamp_s=float(frame / 30),
            controlled_rays=int(valid.sum()),
            generated_valid_controlled_rays=int(matched.sum()),
            coverage=float(matched.sum() / max(1, valid.sum())),
            range_mae_m=float(error.mean()) if error.size else None,
            range_median_error_m=float(np.median(error)) if error.size else None,
            fraction_all_controlled_rays_within_2m=float((error < 2).sum() / max(1, valid.sum())),
        )
    )
report = dict(
    scope="Diagnostics on sparse input HD-map rays; no physical-consistency pass/fail threshold. RGB labels are not inferred from these diagnostics.",
    scan_pose_note="Generated spinning sweep is compared directly with its original motion-aware geometric control; output points are not deskewed.",
    sweeps=records,
)
(out / "control_depth_agreement.json").write_text(json.dumps(report, indent=2) + "\n")
selected = [0, len(records) // 2, len(records) - 1]
figure, axes = plt.subplots(1, 3, figsize=(15, 5), sharex=True, sharey=True)
for ax, index in zip(axes, selected, strict=True):
    frame = records[index]["frame_id"]
    ctrl = control[:, frame // 3]
    cg, _ = range_map_to_xyz(ctrl[0], ctrl[2] > 0.5, range_projection=projection)
    rg = generated["range_m"][index]
    pg, _ = range_map_to_xyz(rg, rg > 0, range_projection=projection)
    pg = pg[:: max(1, len(pg) // 35000)]
    cg = cg[:: max(1, len(cg) // 12000)]
    ax.scatter(pg[:, 0], pg[:, 1], s=0.3, c="#219db7", label="Generated LiDAR", rasterized=True)
    ax.scatter(cg[:, 0], cg[:, 1], s=0.8, c="#ed9a36", label="Input geometry", rasterized=True)
    ax.set(
        xlim=(-15, 65),
        ylim=(-25, 25),
        aspect="equal",
        title=f"t={frame / 30:.2f} s",
        xlabel="Sensor X forward / m",
    )
    ax.grid(alpha=0.2)
axes[0].set_ylabel("Sensor Y left / m")
axes[0].legend(markerscale=5)
figure.suptitle("Generated LiDAR and trajectory-dependent geometric control")
figure.tight_layout()
figure.savefig(out / "lidar_control_overlay.png", dpi=160)
plt.close(figure)
checksums = []
for path in sorted(bundle.rglob("*")):
    if path.is_file() and path.name != "SHA256SUMS":
        with path.open("rb") as file:
            digest = hashlib.file_digest(file, "sha256").hexdigest()
        checksums.append(f"{digest}  {path.relative_to(bundle)}")
(bundle / "SHA256SUMS").write_text("\n".join(checksums) + "\n")
print(json.dumps(report, indent=2), flush=True)
