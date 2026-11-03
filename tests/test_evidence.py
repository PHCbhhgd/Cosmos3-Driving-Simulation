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
    def test_readme_gallery_frames_match_original_bundle_sources(self):
        images = read("media/scenarios/provenance.json")["images"]
        self.assertEqual(len(images), 8)
        for row in images:
            image = ROOT / "media/scenarios" / row["file"]
            self.assertEqual(hashlib.sha256(image.read_bytes()).hexdigest(), row["sha256"])
            original = ROOT / "reports/robustness/transfer-business" / row["case"]
            hashes = dict(
                reversed(line.split("  ", 1))
                for line in (original / "original-bundle-SHA256SUMS").read_text().splitlines()
            )
            self.assertEqual(hashes[row["source_bundle_file"]], row["source_sha256"])
            self.assertTrue(all(0 <= frame <= 60 for frame in row["frame_ids"]))
            self.assertEqual(row["fps"], 30)

    def test_business_previews_are_tied_to_validated_original_sensor_bundles(self):
        base = ROOT / "reports/robustness/transfer-business"
        generated = 0
        for folder in sorted(p for p in base.iterdir() if p.is_dir()):
            run = json.loads((folder / "run.json").read_text())
            if run["status"] != "generated_and_packaged":
                continue
            generated += 1
            with self.subTest(case=folder.name):
                for key in [
                    "package_exit_code",
                    "review_exit_code",
                    "geometry_diagnostics_exit_code",
                    "browser_exit_code",
                ]:
                    self.assertEqual(run[key], 0)
                manifest = json.loads((folder / "bundle_manifest.json").read_text())
                self.assertEqual((len(manifest["cameras"]), manifest["camera_frames"]), (7, 61))
                self.assertTrue(all(row["full_decode"] for row in manifest["cameras"]))
                self.assertEqual([s["frame_id"] for s in manifest["sweeps"]], list(range(0, 60, 3)))
                hashes = dict(
                    reversed(line.split("  ", 1))
                    for line in (folder / "original-bundle-SHA256SUMS").read_text().splitlines()
                )
                previews = read(f"media/robustness/transfer-{folder.name}-previews.json")
                for preview in previews["files"]:
                    public = ROOT / "media/robustness" / preview["file"]
                    self.assertEqual(
                        hashlib.sha256(public.read_bytes()).hexdigest(), preview["sha256"]
                    )
                    self.assertEqual(
                        hashes[preview["original_bundle_file"]], preview["original_sha256"]
                    )
        self.assertEqual(generated, 7)

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

    def test_duration_outputs_and_continuation_match_decoded_evidence(self):
        base = ROOT / "reports/robustness/transfer-duration"
        rows = json.loads((base / "summary.json").read_text())["cases"]
        self.assertEqual({r["expected_frames"] for r in rows}, {121, 241, 397, 793})
        for row in rows:
            folder = base / row["case"]
            self.assertEqual(row["status"], "generated_and_decoded")
            report = json.loads((folder / "video_diagnostics.json").read_text())
            self.assertTrue(report["full_decode"])
            self.assertEqual(report["frames"], row["expected_frames"])
            self.assertEqual(report["fps"], 30)
            control = json.loads((folder / "rgb-control.json").read_text())
            self.assertEqual(control["rgb_sha256"], report["sha256"])
            if row["chunks"] == 2:
                self.assertEqual(row["caption_ranges"], [[0, 400], [396, 796]])
                self.assertTrue(set(range(393, 401)) <= set(report["selected_frame_ids"]))
        for row in read("media/scenarios/provenance.json")["duration_images"]:
            self.assertEqual(
                hashlib.sha256((ROOT / "media/scenarios" / row["file"]).read_bytes()).hexdigest(),
                row["sha256"],
            )
            self.assertEqual(read(row["source_report"])["sha256"], row["source_sha256"])

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
