"""Desktop adapter: unchanged backend, per-launch identity, private pipe shutdown."""
from pathlib import Path
import os
import sys
import threading


def main():
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "app" / "backend"))
    import server

    identity = os.environ["LEDGER_DESKTOP_ID"]
    if sys.stdin is None:
        raise RuntimeError("Desktop server requires its private parent pipe.")
    ready = threading.Event()
    holder = []

    class DesktopHandler(server.Handler):
        def _api(self, method, path):
            if path == "/api/health":
                return self._json(200, {"ok": True, "desktop_instance": identity})
            return super()._api(method, path)

    class DesktopServer(server.ThreadingHTTPServer):
        def server_activate(self):
            super().server_activate()
            holder.append(self)
            ready.set()

    def parent_pipe():
        # A closed parent pipe also shuts down our child after an unexpected launcher exit.
        sys.stdin.buffer.readline()
        ready.wait()
        holder[0].shutdown()

    server.Handler = DesktopHandler
    server.ThreadingHTTPServer = DesktopServer
    threading.Thread(target=parent_pipe, daemon=True).start()
    try:
        server.main()
    finally:
        if holder:
            holder[0].server_close()
        server.scheduler.stop()


if __name__ == "__main__":
    main()
