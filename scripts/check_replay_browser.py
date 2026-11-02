"""Exercise replay with real Chromium video decoding over a local-only HTTP server."""

import argparse
from functools import partial
import http.server
import json
import os
from pathlib import Path
import threading
from serve_replay import ReplayHandler

from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument("bundle", type=Path)
parser.add_argument("--report", type=Path, required=True)
args = parser.parse_args()
bundle = args.bundle.resolve()


class QuietHandler(ReplayHandler):
    def log_message(self, *args):
        pass


server = http.server.ThreadingHTTPServer(
    ("127.0.0.1", 0), partial(QuietHandler, directory=str(bundle))
)
threading.Thread(target=server.serve_forever, daemon=True).start()
errors = []
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            **(
                {"executable_path": os.environ["COSMOS3_BROWSER"]}
                if os.environ.get("COSMOS3_BROWSER")
                else {}
            ),
            headless=True,
            args=["--disable-gpu", "--disable-background-networking", "--no-sandbox"],
        )
        page = browser.new_page(viewport={"width": 1440, "height": 1400})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(f"http://127.0.0.1:{server.server_port}/index.html", wait_until="load")
        page.wait_for_function(
            "videos.length === D.cameras.length && videos.every(v=>v.readyState>=2)",
            timeout=60000,
        )
        assert page.locator("#time").input_value() == "0"
        middle = page.evaluate("Math.floor((D.frames-1)/2)")
        page.locator("#time").fill(str(middle))
        page.locator("#time").dispatch_event("input")
        try:
            page.wait_for_function(
                "videos.every(v=>!v.seeking && Math.abs(v.currentTime-frame/D.fps)<.04)"
            )
        except Exception:
            print(
                page.evaluate(
                    "({frame, videos:videos.map(v=>({time:v.currentTime,duration:v.duration,seeking:v.seeking,ready:v.readyState,error:v.error?.message,seekable:Array.from({length:v.seekable.length},(_,i)=>[v.seekable.start(i),v.seekable.end(i)])}))})"
                ),
                flush=True,
            )
            raise
        mid = page.evaluate(
            "({frame,clock:document.getElementById('clock').textContent,times:videos.map(v=>v.currentTime),fps:D.fps})"
        )
        assert mid["frame"] == middle
        original = page.locator("#cloud").screenshot()
        page.mouse.move(300, 400)
        page.mouse.down()
        page.mouse.move(390, 430, steps=5)
        page.mouse.up()
        assert original != page.locator("#cloud").screenshot(), (
            "Point cloud drag must update the view"
        )
        if not page.locator("#mode").is_disabled():
            page.select_option("#mode", "controls")
            page.wait_for_function(
                "videos.every(v=>v.readyState>=2 && !v.seeking && v.src.includes('/controls/') && Math.abs(v.currentTime-frame/D.fps)<.04)"
            )
            page.select_option("#mode", "cameras")
            page.wait_for_function(
                "videos.every(v=>v.readyState>=2 && !v.seeking && v.src.includes('/cameras/') && Math.abs(v.currentTime-frame/D.fps)<.04)"
            )
        page.click("#play")
        page.wait_for_function("frame > " + str(middle + 5), timeout=15000)
        page.click("#play")
        after = page.evaluate("({frame,times:videos.map(v=>v.currentTime)})")
        assert max(after["times"]) - min(after["times"]) < 0.12, after
        assert not errors, errors
        args.report.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(args.report.with_suffix(".png")), full_page=True)
        report = dict(
            status="passed",
            bundle=str(bundle),
            cameras=page.locator("video").count(),
            checks=[
                "video decode",
                "initial slider and timestamp",
                "seek all cameras",
                "point cloud drag",
                "RGB/WSM mode switch where available",
                "playback advances",
                "camera sync under 120 ms",
                "no JS errors",
            ],
            midpoint=mid,
            playback=after,
        )
        args.report.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        browser.close()
finally:
    server.shutdown()
    server.server_close()
