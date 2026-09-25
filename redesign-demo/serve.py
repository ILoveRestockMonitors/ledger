#!/usr/bin/env python3
"""Serve the redesign demo at http://localhost:8000/redesign-demo/ .

Static files only, bound to this computer. Only redesign-demo/ and web/ are
served, so nothing from backend/ or your data directory is reachable.
"""
import http.server
import os
import re
import sys
import webbrowser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOWED = ("/redesign-demo/", "/web/")


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def send_head(self):
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        if path in ("/", "/redesign-demo"):
            self.send_response(302)
            self.send_header("Location", "/redesign-demo/")
            self.end_headers()
            return None
        if not path.startswith(ALLOWED) or ".." in path:
            self.send_error(404)
            return None
        full = self.translate_path(path)
        match = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range", ""))
        if not match or not os.path.isfile(full):
            return super().send_head()
        # Byte ranges let Safari play and loop the background videos.
        size = os.path.getsize(full)
        start = int(match.group(1) or 0)
        end = min(int(match.group(2) or size - 1), size - 1)
        if start > end:
            self.send_error(416)
            return None
        f = open(full, "rb")
        f.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(full))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self._remaining = end - start + 1
        return f

    def copyfile(self, source, outputfile):
        remaining = getattr(self, "_remaining", None)
        if remaining is None:
            return super().copyfile(source, outputfile)
        while remaining > 0:
            chunk = source.read(min(65536, remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            remaining -= len(chunk)
        self._remaining = None

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main():
    port = next((int(a) for a in sys.argv[1:] if a.isdigit()), 8000)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://localhost:{port}/redesign-demo/"
    print(f"Ledger redesign demo: {url}  (Ctrl+C to stop)")
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
