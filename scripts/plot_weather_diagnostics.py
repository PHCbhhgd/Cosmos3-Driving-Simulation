"""Plot matched weather diagnostics; sparse controls are not physical sensor truth."""

import argparse
import json
from pathlib import Path


def plot(reports, output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True, constrained_layout=True)
    for name, label, color in [
        ("clear_turn", "Clear", "#b66d00"),
        ("rain_turn", "Rain", "#1766b7"),
        ("snow_turn", "Snow", "#008577"),
    ]:
        folder = reports / name
        run = json.loads((folder / "run.json").read_text())
        if run["status"] != "generated_and_packaged":
            raise ValueError(f"Not a completed sensor run: {name}")
        depth = json.loads((folder / "control_depth_agreement.json").read_text())["sweeps"]
        actors = json.loads((folder / "actor_support.json").read_text())["sweeps"]
        if [r["frame_id"] for r in depth] != [r["frame_id"] for r in actors]:
            raise ValueError("Depth and actor diagnostics have different sweep IDs")
        times = [r["timestamp_s"] for r in depth]
        values = [
            [r["coverage"] * 100 for r in depth],
            [r["range_mae_m"] for r in depth],
            [r["points_near_actor_box"]["lead_car"] for r in actors],
        ]
        for axis, values_for_axis in zip(axes, values):
            axis.plot(times, values_for_axis, color=color, marker=".", label=label)
    for axis, label in zip(
        axes,
        [
            "Valid controlled rays (%)",
            "Range MAE on valid controlled rays (m)",
            "Points near lead box",
        ],
    ):
        axis.set_ylabel(label)
        axis.grid(alpha=0.25)
        axis.set_ylim(bottom=0)
    axes[0].set_ylim(0, 100)
    axes[0].legend(ncols=3)
    axes[-1].set_xlabel("Sweep start time (s)")
    figure.suptitle(
        "Transfer-Auto: same geometry and seed, different weather captions\n"
        "One sample per weather; sparse-control agreement, not physical accuracy",
        fontsize=12,
    )
    figure.text(
        0.03,
        -0.03,
        "Box counts can include nearby surfaces; sweep-start poses are not deskewed. "
        "No calibrated rain/snow scattering reference.",
        fontsize=8,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=160, bbox_inches="tight")
    plt.close(figure)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("reports", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    plot(args.reports, args.output)


if __name__ == "__main__":
    main()
