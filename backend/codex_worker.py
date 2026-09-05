"""Local bounded entry point and explicit same-profile browser handoff."""
from __future__ import annotations

import argparse
import json
import os
import signal
import shutil
import subprocess

try:
    from . import cancellations
except ImportError:  # ``python backend/codex_worker.py`` / server-style imports
    import cancellations


def run_once():
    return cancellations.run_once()


def status():
    return cancellations.status()


def handoff(job_id):
    """Launch the job's persisted profile visibly for login/MFA/captcha."""
    info = cancellations.handoff_info(job_id)
    lock_fd = cancellations._acquire_profile(info["profile"])
    if lock_fd is None:
        raise RuntimeError("Cancellation browser profile is busy; retry after the other worker/browser ends")
    node = shutil.which(os.environ.get("LEDGER_NODE", "node"))
    mcp_cli = os.environ.get("LEDGER_PLAYWRIGHT_MCP_CLI", cancellations.DEFAULT_MCP_CLI)
    if not node or not os.path.isfile(mcp_cli):
        cancellations._release_profile(lock_fd)
        raise RuntimeError("Install the pinned @playwright/mcp CLI and Node before browser handoff")
    origins = os.environ.get("LEDGER_BROWSER_ALLOWED_ORIGINS", cancellations.DEFAULT_PROVIDERS)
    hosts = os.environ.get("LEDGER_BROWSER_ALLOWED_HOSTS", cancellations.DEFAULT_HOSTS)
    init_page = os.path.join(info["workspace"], "handoff-init.mjs")
    try:
        with open(init_page, "w", encoding="utf-8") as stream:
            stream.write("export default async ({ page }) => { await page.goto(" + json.dumps(info["url"]) + ", { waitUntil: 'domcontentloaded' }); };\n")
    except BaseException:
        cancellations._release_profile(lock_fd)
        raise
    argv = [node, mcp_cli, "--browser", "chromium", "--user-data-dir", info["profile"],
            "--allowed-hosts", hosts, "--allowed-origins", origins, "--init-page", init_page]
    env = cancellations._safe_worker_env(info["workspace"], info["profile"], info["job_id"])
    env["LEDGER_BROWSER_HEADLESS"] = "0"
    try:
        process = subprocess.Popen(argv, cwd=info["workspace"], env=env, shell=False,
                                   start_new_session=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   text=True, bufsize=1)
        process._ledger_profile_lock = lock_fd
    except BaseException:
        cancellations._release_profile(lock_fd)
        raise
    # Complete the MCP handshake and navigate explicitly.  --init-page is
    # retained as a fallback, but this request guarantees the visible headed
    # browser opens the provider URL before the command returns.
    if process.stdin is None or process.stdout is None:
        return process
    try:
        _rpc_roundtrip(process, 1, "initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "ledger-handoff", "version": "1.0"},
        })
        process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}) + "\n")
        process.stdin.flush()
        response = _rpc_roundtrip(process, 2, "tools/call", {
            "name": "browser_navigate", "arguments": {"url": info["url"]},
        })
        if "error" in response:
            raise RuntimeError(str(response["error"].get("message") or "browser navigation failed"))
    except BaseException:
        _terminate_handoff(process)
        cancellations._release_profile(getattr(process, "_ledger_profile_lock", lock_fd))
        process._ledger_profile_lock = None
        raise
    return process


def _terminate_handoff(process):
    """Stop the headed MCP process group, including Chromium children."""
    if process is None:
        return
    try:
        if process.poll() is not None:
            return
    except AttributeError:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (OSError, AttributeError):
        try: process.terminate()
        except Exception: pass
    try:
        process.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired, AttributeError):
        try: os.killpg(process.pid, signal.SIGKILL)
        except (OSError, AttributeError):
            try: process.kill()
            except Exception: pass
        try: process.wait(timeout=5)
        except Exception: pass


def _rpc_roundtrip(process, request_id, method, params):
    # Reuse the receipt worker's bounded, fragmented-stdio-safe RPC reader.
    # Import lazily so this entry point remains usable as a direct script.
    try:
        from . import receipt_worker
    except ImportError:
        import receipt_worker
    return receipt_worker._rpc_roundtrip(process, request_id, method, params)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Ledger local cancellation worker")
    commands = parser.add_subparsers(dest="command", required=True)
    handoff_parser = commands.add_parser("handoff", help="open a queued job's browser profile for user login/MFA")
    handoff_parser.add_argument("job_id")
    commands.add_parser("status", help="show Codex and browser readiness")
    args = parser.parse_args(argv)
    if args.command == "status":
        print(__import__("json").dumps(status()))
        return 0
    def _signal_to_interrupt(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGINT, _signal_to_interrupt)
    signal.signal(signal.SIGTERM, _signal_to_interrupt)
    process = handoff(args.job_id)
    try:
        return process.wait()
    except (KeyboardInterrupt, SystemExit):
        _terminate_handoff(process)
        raise
    finally:
        cancellations._release_profile(getattr(process, "_ledger_profile_lock", None))
        process._ledger_profile_lock = None


if __name__ == "__main__":
    raise SystemExit(main())
