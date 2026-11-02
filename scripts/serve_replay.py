"""Serve replay bundles with byte ranges so browsers can seek all camera MP4s."""

import argparse
from functools import partial
import http.server
from pathlib import Path
import re


class ReplayHandler(http.server.SimpleHTTPRequestHandler):
    def send_head(self):
        self._range_remaining = None
        path = Path(self.translate_path(self.path))
        if not path.is_file():
            return super().send_head()
        size = path.stat().st_size
        start, end = 0, size - 1
        requested = self.headers.get("Range")
        if requested:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested.strip())
            if match and any(match.groups()):
                first, last = match.groups()
                if first:
                    start = int(first)
                    end = min(int(last), size - 1) if last else size - 1
                else:
                    start = max(0, size - int(last))
            else:
                start = size
            if not 0 <= start <= end < size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return None
        file = path.open("rb")
        file.seek(start)
        self._range_remaining = max(0, end - start + 1)
        self.send_response(206 if requested else 200)
        self.send_header("Content-Type", self.guess_type(str(path)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(self._range_remaining))
        if requested:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        return file

    def copyfile(self, source, outputfile):
        if self._range_remaining is None:
            return super().copyfile(source, outputfile)
        remaining = self._range_remaining
        try:
            while remaining:
                data = source.read(min(remaining, 65536))
                if not data:
                    break
                outputfile.write(data)
                remaining -= len(data)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Browser cancelled an old range while seeking.


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, nargs="?", default=Path(__file__).resolve().parent)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--bind", default="127.0.0.1")
    args = parser.parse_args()
    server = http.server.ThreadingHTTPServer(
        (args.bind, args.port),
        partial(ReplayHandler, directory=str(args.directory.resolve())),
    )
    print(f"Replay: http://{args.bind}:{server.server_port}/index.html", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
