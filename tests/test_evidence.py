"""Check that public claims are supported by the committed run evidence."""

import csv
import hashlib
import json
from pathlib import Path
import statistics
import unittest

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT / name).read_text())


class EvidenceTests(unittest.TestCase):
    def test_robustness_nano_videos_match_full_decode_reports(self):
        aliases = {
            "nano-duration-20261103-r2": "nano-duration",
            "nano-business-20261103": "nano-business",
            "nano-motion-duration-20261103": "nano-motion-duration",
            "nano-contact-20261103": "nano-contact",
        }
        generated, rejected = 0, 0
        for suite, alias in aliases.items():
            base = f"reports/robustness/nano/{suite}"
            for row in read(f"{base}/results.json"):
                case = row.get("id", f"frames-{row['frames']}")
                if row["status"] == "generated":
                    video = ROOT / f"media/robustness/{alias}-{case}.mp4"
                    report = read(f"{base}/{case}/video_diagnostics.json")
                    self.assertEqual(
                        hashlib.sha256(video.read_bytes()).hexdigest(), row["video_sha256"]
                    )
                    self.assertEqual(report["sha256"], row["video_sha256"])
                    self.assertEqual(report["frames"], row["frames"])
                    self.assertTrue(report["full_decode"])
                    generated += 1
                else:
                    self.assertIn("Guardrail", row["error"])
                    rejected += 1
        self.assertEqual((generated, rejected), (11, 1))

    def test_lidar_boundary_evidence_is_not_model_generation(self):
        report = read("reports/robustness/lidar-boundaries.json")
        self.assertIn("no denoiser", report["method"])
        for row in report["results"]:
            expected = 5 <= row["input_range_m"] <= 100 and row["input_validity"] >= 0.5
            self.assertEqual(row["encoded_valid_fraction"], float(expected))
            self.assertEqual(row["saved_nonzero_fraction"], float(expected))

    def test_transfer_sensor_clocks_and_diagnostics(self):
        summary = read("reports/summary.json")["models"]["Cosmos3-Nano-Transfer-Auto"]
        for variant in ["straight", "left_shift"]:
            with self.subTest(variant=variant):
                prefix = f"reports/transfer/{variant}"
                manifest = read(f"{prefix}/bundle_manifest.json")
                self.assertEqual(manifest["status"], "passed")
                self.assertEqual((len(manifest["cameras"]), manifest["camera_frames"]), (7, 61))
                self.assertEqual((manifest["camera_fps"], manifest["lidar_fps"]), (30, 10))
                for camera in manifest["cameras"]:
                    self.assertTrue(camera["full_decode"])
                    stream = camera["stream"]
                    self.assertEqual(
                        (stream["width"], stream["height"], int(stream["nb_read_frames"])),
                        (832, 480, 61),
                    )
                self.assertEqual([s["frame_id"] for s in manifest["sweeps"]], list(range(0, 60, 3)))
                for sweep in manifest["sweeps"]:
                    self.assertAlmostEqual(sweep["timestamp_s"], sweep["frame_id"] / 30)
                    self.assertGreater(sweep["points"], 100000)
                records = read(f"{prefix}/control_depth_agreement.json")["sweeps"]
                expected = next(g for g in summary["generations"] if g["variant"] == variant)
                self.assertAlmostEqual(
                    statistics.mean(r["coverage"] for r in records),
                    expected["geometry_diagnostic"]["mean_valid_coverage"],
                )
                self.assertAlmostEqual(
                    statistics.mean(r["range_mae_m"] for r in records),
                    expected["geometry_diagnostic"]["mean_sweep_range_mae_m"],
                )
                with (ROOT / prefix / "input_trajectory.csv").open() as handle:
                    poses = list(csv.DictReader(handle))
                self.assertAlmostEqual(float(poses[60]["ego_x_m"]), 8)
                self.assertAlmostEqual(
                    float(poses[60]["ego_y_m"]), 1 if variant == "left_shift" else 0
                )
                browser = read(f"{prefix}/browser_validation.json")
                self.assertEqual((browser["status"], browser["cameras"]), ("passed", 7))

    def test_nano_hash_and_sim_failure_scope(self):
        nano = read("reports/nano/result.json")
        validation = read("reports/nano/video_validation.json")
        self.assertEqual(nano["video_sha256"], validation["video_sha256"])
        self.assertTrue(nano["settings"]["safety_checker"])
        self.assertTrue(validation["full_decode"])
        sim = read("reports/hardware/sim_auto.json")
        self.assertEqual(sim["status"], "unsupported_hardware")
        self.assertEqual(sim["compute_capability"], [8, 9])

    def test_media_inventory_and_pinned_versions(self):
        for row in read("configs/media-manifest.json")["files"]:
            path = ROOT / row["file"]
            self.assertEqual(path.stat().st_size, row["bytes"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["sha256"])
        versions = read("configs/versions.json")
        for model in versions["models"].values():
            self.assertRegex(model["revision"], r"^[0-9a-f]{40}$")
        self.assertRegex(versions["source"]["commit"], r"^[0-9a-f]{40}$")
        self.assertEqual(
            hashlib.sha256((ROOT / "patches/framework-low-memory.patch").read_bytes()).hexdigest(),
            versions["patch_sha256"],
        )
        for case in read("configs/test-matrix.json")["cases"]:
            self.assertTrue((ROOT / case["evidence"]).is_file())


if __name__ == "__main__":
    unittest.main()
