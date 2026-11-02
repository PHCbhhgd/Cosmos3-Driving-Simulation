"""Select a leading camera interval while aligning native caption chunk boundaries."""

import copy
import json
from pathlib import Path


def shorten_request(request: dict, scene: Path, frames: int) -> dict:
    available = request["num_frames"]
    if frames < 1 or (frames - 1) % 4 or frames > available:
        raise ValueError("frames must be 4k+1 and covered by input controls")
    result = copy.deepcopy(request)
    result.update(
        name=f"{request['name']}_{frames}", num_frames=frames, num_video_frames_per_chunk=frames
    )
    caption_dir = scene / f"captions-{frames}"
    caption_dir.mkdir(exist_ok=True)
    for view in result["multiview"]["views"]:
        original = json.loads((scene / view["caption_path"]).read_text())
        chunks = original["caption_structured"]
        first = min(chunks.values(), key=lambda c: c["start_frame"])
        if first["start_frame"] != 0 or first["end_frame"] < frames:
            raise ValueError("Caption does not cover the requested first interval")
        caption = copy.deepcopy(original)
        caption["caption_structured"] = {
            f"chunk_0_{frames + 3}": first | {"start_frame": 0, "end_frame": frames + 3}
        }
        path = caption_dir / f"{view['camera_key']}.json"
        path.write_text(json.dumps(caption, indent=2) + "\n")
        view["caption_path"] = str(path.relative_to(scene))
    return result
