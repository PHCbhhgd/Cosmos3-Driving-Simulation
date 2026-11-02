"""Check a Nano result's hash, video metadata, full decoding and preview frames."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("output", type=Path)
args = parser.parse_args()
output = args.output.resolve()
request = json.loads((output / "request.json").read_text())
result = json.loads((output / "result.json").read_text())
assert result["status"] == "generated", result
video = output / "video.mp4"
prefix = ["bash", str(ROOT / "scripts/run_env.sh"), "bash", str(ROOT / "scripts/ubuntu_env.sh")]
probe = subprocess.check_output(
    prefix
    + [
        "ffprobe",
        "-v",
        "error",
        "-count_frames",
        "-show_entries",
        "stream=codec_name,width,height,r_frame_rate,nb_read_frames,duration",
        "-of",
        "json",
        str(video),
    ],
    text=True,
)
stream = json.loads(probe)["streams"][0]
assert (stream["width"], stream["height"]) == (request["width"], request["height"]), stream
assert int(stream["nb_read_frames"]) == request["frames"], stream
numerator, denominator = map(int, stream["r_frame_rate"].split("/"))
assert numerator / denominator == request["fps"], stream
with video.open("rb") as handle:
    digest = hashlib.file_digest(handle, "sha256").hexdigest()
assert digest == result["video_sha256"]
subprocess.run(
    prefix + ["ffmpeg", "-v", "error", "-xerror", "-i", str(video), "-f", "null", "-"], check=True
)
indices = [0, request["frames"] // 2, request["frames"] - 1]
selection = "+".join(f"eq(n\\,{index})" for index in indices)
subprocess.run(
    prefix
    + [
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-i",
        str(video),
        "-vf",
        f"select={selection},tile=3x1",
        "-frames:v",
        "1",
        "-update",
        "1",
        str(output / "preview.jpg"),
    ],
    check=True,
)
report = dict(
    status="passed",
    video_sha256=digest,
    stream=stream,
    full_decode=True,
    preview_frame_indices=indices,
    scope="File integrity and encoding checks; visual quality requires separate inspection",
)
(output / "video_validation.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
