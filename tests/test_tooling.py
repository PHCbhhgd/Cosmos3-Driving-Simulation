"""CPU contract tests for release integrity, replay seeking and caption windows."""

import copy
from functools import partial
import http.client
import http.server
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_release import copy_bundle, digest, verify  # noqa: E402
from request_window import shorten_request  # noqa: E402
from serve_replay import ReplayHandler  # noqa: E402
from collect_robustness import collect  # noqa: E402
from build_duration_release import build as build_duration  # noqa: E402
from audit_release_archive import audit as audit_archive  # noqa: E402


class BenchmarkCollectionTests(unittest.TestCase):
    def test_pending_and_missing_results_are_not_reported_as_passes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            suite = root / "suite"
            (suite / "pending").mkdir(parents=True)
            (suite / "no-record").mkdir()
            (suite / "pending/run.json").write_text(
                json.dumps(
                    {"status": "running", "case": "pending", "path": str(root / "raw/output.mp4")}
                )
            )
            report = collect(suite, root / "reports", source_root=root)
            self.assertEqual(len(report["cases"]), 1)
            self.assertEqual(report["cases"][0]["status"], "running")
            self.assertEqual(report["cases"][0]["path"], "raw/output.mp4")
            self.assertFalse((root / "reports/no-record").exists())


class QuietHandler(ReplayHandler):
    def log_message(self, *args):
        pass


class ReplayRangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        root = Path(cls.temporary.name)
        (root / "video.mp4").write_bytes(b"0123456789")
        (root / "empty.mp4").write_bytes(b"")
        cls.server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), partial(QuietHandler, directory=str(root))
        )
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temporary.cleanup()

    def request(self, byte_range=None, method="GET", path="/video.mp4"):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        headers = {"Range": byte_range} if byte_range else {}
        connection.request(method, path, headers=headers)
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_whole_video_and_head(self):
        status, headers, body = self.request()
        self.assertEqual((status, body), (200, b"0123456789"))
        self.assertEqual(headers["Accept-Ranges"], "bytes")
        status, headers, body = self.request("bytes=2-5", method="HEAD")
        self.assertEqual((status, body, headers["Content-Length"]), (206, b"", "4"))

    def test_seek_ranges(self):
        for value, expected, content_range in [
            ("bytes=2-5", b"2345", "bytes 2-5/10"),
            ("bytes=7-", b"789", "bytes 7-9/10"),
            ("bytes=-3", b"789", "bytes 7-9/10"),
            ("bytes=8-99", b"89", "bytes 8-9/10"),
        ]:
            with self.subTest(value=value):
                status, headers, body = self.request(value)
                self.assertEqual(
                    (status, body, headers["Content-Range"]), (206, expected, content_range)
                )
                self.assertEqual(int(headers["Content-Length"]), len(expected))

    def test_reject_invalid_and_multiple_ranges(self):
        for value in ["bytes=10-", "bytes=6-2", "bytes=-0", "bytes=", "bytes=0-1,4-5"]:
            with self.subTest(value=value):
                status, headers, body = self.request(value)
                self.assertEqual((status, body, headers["Content-Range"]), (416, b"", "bytes */10"))

    def test_empty_file(self):
        self.assertEqual(self.request(path="/empty.mp4")[::2], (200, b""))
        self.assertEqual(self.request("bytes=0-", path="/empty.mp4")[0], 416)


class CaptionWindowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.scene = Path(self.temporary.name)
        (self.scene / "captions").mkdir()
        (self.scene / "captions/front.json").write_text(
            json.dumps(
                {
                    "caption_structured": {
                        "chunk_0_124": {"caption": "Test scene", "start_frame": 0, "end_frame": 124}
                    }
                }
            )
        )
        self.request = {
            "name": "trajectory_straight",
            "num_frames": 121,
            "num_video_frames_per_chunk": 121,
            "multiview": {
                "views": [
                    {
                        "camera_key": "front",
                        "caption_path": "captions/front.json",
                        "control_path": "controls/front.mp4",
                    }
                ]
            },
        }

    def tearDown(self):
        self.temporary.cleanup()

    def test_shorten_aligns_captions_without_retiming_controls(self):
        original = copy.deepcopy(self.request)
        result = shorten_request(self.request, self.scene, 61)
        self.assertEqual(self.request, original)
        self.assertEqual((result["num_frames"], result["name"]), (61, "trajectory_straight_61"))
        view = result["multiview"]["views"][0]
        self.assertEqual(view["control_path"], "controls/front.mp4")
        caption = json.loads((self.scene / view["caption_path"]).read_text())
        self.assertEqual(
            caption["caption_structured"]["chunk_0_64"],
            {"caption": "Test scene", "start_frame": 0, "end_frame": 64},
        )
        self.assertTrue((self.scene / "captions/front.json").exists())

    def test_reject_uncovered_or_invalid_length(self):
        for frames in [0, 60, 125]:
            with self.subTest(frames=frames), self.assertRaises(ValueError):
                shorten_request(self.request, self.scene, frames)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "sample.json").write_text(
            json.dumps({"path": str(self.root / "run/output.mp4")})
        )
        (self.source / "video.mp4").write_bytes(b"example video fixture")
        (self.source / "SHA256SUMS").write_text(
            "".join(
                f"{digest(p)}  {p.name}\n"
                for p in sorted(self.source.iterdir())
                if p.name != "SHA256SUMS"
            )
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_path_redaction_regenerates_valid_inventory(self):
        destination = self.root / "public"
        copy_bundle(self.source, destination, self.root)
        self.assertEqual(
            json.loads((destination / "sample.json").read_text())["path"], "run/output.mp4"
        )
        self.assertEqual(verify(destination)["video.mp4"], digest(self.source / "video.mp4"))
        self.assertNotEqual(
            digest(destination / "sample.json"), digest(self.source / "sample.json")
        )

    def test_reject_tampering_and_unlisted_files(self):
        (self.source / "video.mp4").write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            verify(self.source)
        (self.source / "unlisted.json").write_text("{}")
        (self.source / "video.mp4").write_bytes(b"example video fixture")
        with self.assertRaisesRegex(ValueError, "unlisted files"):
            verify(self.source)

    def test_reject_source_symlink(self):
        (self.source / "video.mp4").unlink()
        (self.source / "video.mp4").symlink_to(self.source / "sample.json")
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            verify(self.source)


class DurationReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.suite = self.root / "suite"
        self.scene = self.root / "scene"
        self.scene.mkdir()
        (self.scene / "scene_manifest.json").write_text(
            json.dumps({"benchmark_case": {"geometry": "tunnel_entry"}})
        )
        self.folder = self.suite / "front-rgb-121"
        raw = self.folder / "raw/front-rgb-121"
        raw.mkdir(parents=True)
        self.video = raw / "vision_test.mp4"
        self.video.write_bytes(b"original video byte-integrity fixture, not a real video")
        (self.folder / "review").mkdir()
        (self.folder / "review/video_diagnostics.json").write_text(
            json.dumps({"full_decode": True, "frames": 121, "sha256": digest(self.video)})
        )
        self.row = {
            "case": "front-rgb-121",
            "status": "generated_and_decoded",
            "expected_frames": 121,
        }
        self.write_records()

    def tearDown(self):
        self.temporary.cleanup()

    def write_records(self):
        (self.folder / "run.json").write_text(json.dumps(self.row | {"source": str(self.video)}))
        (self.suite / "results.json").write_text(json.dumps([self.row]))

    def build(self):
        return build_duration(
            self.suite,
            self.scene,
            self.root / "release",
            self.root,
            cases=["front-rgb-121"],
            archive_name="tunnel",
        )

    def test_archive_preserves_original_bytes_and_redacts_metadata(self):
        self.build()
        self.assertEqual(audit_archive(self.root / "release/tunnel.tar.gz")["status"], "passed")
        with tarfile.open(self.root / "release/tunnel.tar.gz") as archive:
            prefix = "tunnel/runs/front-rgb-121/"
            self.assertEqual(
                archive.extractfile(prefix + "raw/front-rgb-121/vision_test.mp4").read(),
                self.video.read_bytes(),
            )
            record = json.load(archive.extractfile(prefix + "run.json"))
            self.assertFalse(record["source"].startswith(str(self.root)))
        # Failed requests must remain visible, without requiring a non-existent video.
        self.row["status"] = "failed"
        self.write_records()
        failure_output = self.root / "failure-release"
        result = build_duration(
            self.suite, self.scene, failure_output, self.root, cases=["front-rgb-121"]
        )
        self.assertEqual(result["generated_cases"], [])

    def test_incomplete_and_tampered_output_cannot_be_released(self):
        self.row["status"] = "running"
        self.write_records()
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.build()
        self.row["status"] = "generated_and_decoded"
        self.write_records()
        self.video.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "disagrees"):
            self.build()


if __name__ == "__main__":
    unittest.main()
