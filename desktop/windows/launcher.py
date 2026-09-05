"""Hidden Windows launcher. Financial records remain outside the installed app."""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request


PORT = 8907
URL = f"http://127.0.0.1:{PORT}/"


def data_directory(environ=None):
    env = os.environ if environ is None else environ
    base = env.get("LOCALAPPDATA")
    if not base:
        raise RuntimeError("Windows could not locate your local application data folder.")
    return Path(base) / "LedgerPersonal"


def validate_data(directory):
    """Fail closed on a wrong/damaged folder; never import or overwrite a database."""
    if not directory.exists():
        return
    if not directory.is_dir():
        raise RuntimeError(f"Your Ledger data path is not a folder: {directory}")
    database = directory / "ledger.db"
    if not database.exists():
        # A failed first start may have written only our logs.
        extras = [p for p in directory.iterdir() if p.name not in {"desktop.log", "desktop.log.1"}]
        if extras:
            raise RuntimeError(f"This folder contains files but no Ledger database:\n{directory}\n\n"
                               "Keep these files. Ask for help selecting your existing Ledger data.")
        return
    try:
        connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
        try:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"accounts", "transactions"}.issubset(tables):
                raise ValueError("Not a Ledger database")
            if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("Database check failed")
        finally:
            connection.close()
    except (sqlite3.Error, ValueError) as exc:
        raise RuntimeError(f"Ledger could not safely open your existing database:\n{database}\n\n"
                           "Your files have been left in place. Restore a backup or ask for help.") from exc


def ensure_port_available(port=PORT):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if os.name == "nt":
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as exc:
            raise RuntimeError("Ledger's address is already in use. If your old command window is still "
                               "running Ledger, stop it with Ctrl+C once, then click Ledger again. "
                               "No other program has been stopped.") from exc


def child_environment(directory, identity):
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(
        ("LEDGER_", "OPENAI_", "ANTHROPIC_", "PLAID_", "CODEX_"))}
    env.update(LEDGER_DATA_DIR=str(directory), LEDGER_PORT=str(PORT),
               LEDGER_BIND_HOST="127.0.0.1", LEDGER_DESKTOP_ID=identity)
    return env


def wait_ready(process, identity, url=URL, timeout=25):
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Ledger could not start. Its local log has the details.")
        try:
            with client.open(url + "api/health", timeout=1) as response:
                health = json.loads(response.read(4096))
            if health.get("desktop_instance") == identity and health.get("ok") is True:
                if process.poll() is None:
                    return
        except (OSError, ValueError, urllib.error.URLError):
            pass
        time.sleep(0.1)
    raise RuntimeError("Ledger did not finish starting. Try again, or ask for help with its local log.")


def stop_child(process):
    """Ask only our own child to close; retain SQLite's normal WAL recovery on timeout."""
    if process.poll() is not None:
        return
    try:
        process.stdin.write(b"stop\n")
        process.stdin.flush()
        process.stdin.close()
        process.wait(timeout=12)
    except (OSError, subprocess.TimeoutExpired):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def run(stop=False):
    from win_ui import Instance, message, open_window
    directory = data_directory()
    instance = Instance(directory)
    process = None
    try:
        if not instance.acquire():
            instance.signal("stop" if stop else "open")
            if stop:
                deadline = time.monotonic() + 35
                while time.monotonic() < deadline:
                    if instance.acquire():
                        message("Ledger has stopped. Your saved records are safe to back up.")
                        return
                    time.sleep(0.1)
                raise RuntimeError("Ledger is still closing. Wait a moment and try Stop Ledger again.")
            return
        if stop:
            message("Ledger is already stopped. Your saved records are still on this computer.")
            return
        # Reserve ownership and reject an old/manual server before touching the database.
        ensure_port_available()
        validate_data(directory)
        root = Path(__file__).resolve().parents[2]
        # The console interpreter reliably provides redirected stdin for shutdown.
        # CREATE_NO_WINDOW below keeps it invisible; only the supervisor uses pythonw.
        python = root / "runtime" / "python.exe"
        host = root / "desktop" / "windows" / "server_host.py"
        if not python.is_file() or not (root / "app" / "backend" / "server.py").is_file():
            raise RuntimeError("Ledger's application files are missing. Run INSTALL-LEDGER again.")
        directory.mkdir(parents=True, exist_ok=True)
        log_path = directory / "desktop.log"
        if log_path.exists() and log_path.stat().st_size > 1_000_000:
            log_path.replace(directory / "desktop.log.1")
        identity = secrets.token_hex(24)
        with log_path.open("ab", buffering=0) as log:
            process = subprocess.Popen([str(python), str(host)], cwd=root,
                                       env=child_environment(directory, identity), stdin=subprocess.PIPE,
                                       stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
            wait_ready(process, identity)
            open_window(URL)
            while process.poll() is None:
                request = instance.wait(1000)
                if request == "stop":
                    stop_child(process)
                    return
                if request == "open":
                    open_window(URL)
            raise RuntimeError("Ledger stopped unexpectedly. Click its desktop icon to reopen it.")
    except Exception as exc:
        message(f"{exc}\n\nLocal log (if created):\n{directory / 'desktop.log'}", error=True)
    finally:
        if process is not None:
            stop_child(process)
        instance.close()


if __name__ == "__main__":
    try:
        if os.name != "nt":
            raise RuntimeError("This package is for Windows. Use the standard Ledger package on other computers.")
        run(stop="--stop" in sys.argv)
    except Exception as exc:
        if os.name == "nt":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, str(exc), "Ledger", 0x10)
        else:
            raise
