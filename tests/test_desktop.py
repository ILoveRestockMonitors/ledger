"""Desktop lifecycle tests use isolated databases and never launch a real browser."""
import hashlib
import http.cookiejar
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("desktop_launcher", ROOT / "desktop/windows/launcher.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class DesktopDataTests(unittest.TestCase):
    def test_prior_windows_location_is_preserved(self):
        self.assertEqual(launcher.data_directory({"LOCALAPPDATA": "/Users/Example User/Local"}),
                         Path("/Users/Example User/Local/LedgerPersonal"))

    def test_no_fallback_when_local_app_data_is_missing(self):
        with self.assertRaises(RuntimeError):
            launcher.data_directory({})

    def test_existing_invalid_data_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t)
            (path / "ledger.db").write_bytes(b"not a database")
            before = (path / "ledger.db").read_bytes()
            with self.assertRaises(RuntimeError):
                launcher.validate_data(path)
            self.assertEqual(before, (path / "ledger.db").read_bytes())

    def test_nonempty_folder_is_not_silently_initialized(self):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t)
            (path / "config.json").write_text("{}")
            with self.assertRaises(RuntimeError):
                launcher.validate_data(path)
            self.assertFalse((path / "ledger.db").exists())

    def test_clean_first_run_and_failed_start_log_are_accepted(self):
        with tempfile.TemporaryDirectory() as t:
            launcher.validate_data(Path(t))
            (Path(t) / "desktop.log").write_text("startup failed")
            launcher.validate_data(Path(t))

    def test_another_service_on_port_is_not_stopped(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = listener.getsockname()[1]
            with self.assertRaises(RuntimeError):
                launcher.ensure_port_available(port)
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                pass

    def test_inherited_demo_port_and_credentials_do_not_reconfigure_desktop(self):
        from unittest.mock import patch
        with patch.dict(os.environ, {"LEDGER_DEMO": "1", "LEDGER_DATA_DIR": "/wrong",
                                     "OPENAI_API_KEY": "test-only", "LEDGER_PORT": "1234"}):
            env = launcher.child_environment(Path("/right"), "test-identity")
        self.assertNotIn("LEDGER_DEMO", env)
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertEqual(env["LEDGER_DATA_DIR"], "/right")
        self.assertEqual(env["LEDGER_PORT"], "8907")


class DesktopLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ledger desktop ü ")
        self.root = Path(self.temp.name)
        (self.root / "desktop/windows").mkdir(parents=True)
        shutil.copy(ROOT / "desktop/windows/server_host.py", self.root / "desktop/windows/server_host.py")
        shutil.copytree(ROOT / "backend", self.root / "app/backend",
                        ignore=shutil.ignore_patterns("data", "__pycache__", "*.pyc"))
        shutil.copytree(ROOT / "web", self.root / "app/web")
        self.data = self.root / "personal records"
        with socket.socket() as port:
            port.bind(("127.0.0.1", 0))
            self.port = port.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}/"
        self.process = None

    def tearDown(self):
        if self.process:
            launcher.stop_child(self.process)
            self.process.stdout.close()
        self.temp.cleanup()

    def start(self):
        env = launcher.child_environment(self.data, "isolated-desktop-test")
        env.update(LEDGER_PORT=str(self.port), LEDGER_TESTING="1")
        self.process = subprocess.Popen([sys.executable, str(self.root / "desktop/windows/server_host.py")],
                                        env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT)
        launcher.wait_ready(self.process, "isolated-desktop-test", self.url, timeout=10)

    def test_first_setup_stop_restart_preserves_owner_and_record(self):
        self.start()
        client = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        request = urllib.request.Request(self.url + "api/auth/setup",
                    data=json.dumps({"password": "DesktopFixture-password-2026"}).encode(),
                    headers={"Content-Type": "application/json", "X-Ledger-Request": "1", "Origin": self.url[:-1]})
        with client.open(request) as response:
            self.assertTrue(json.load(response)["ok"])
        with client.open(self.url + "api/accounts") as response:
            self.assertEqual(json.load(response), [])
        # A synthetic durable marker represents an existing record, not real financial data.
        with sqlite3.connect(self.data / "ledger.db") as db:
            db.execute("CREATE TABLE desktop_test_record (value TEXT)")
            db.execute("INSERT INTO desktop_test_record VALUES ('preserve me')")
        launcher.stop_child(self.process)
        self.assertEqual(self.process.returncode, 0, self.process.stdout.read().decode())
        self.process.stdout.close()
        launcher.validate_data(self.data)
        self.start()
        with urllib.request.urlopen(self.url + "api/auth/status") as response:
            self.assertTrue(json.load(response)["configured"])
        with sqlite3.connect(self.data / "ledger.db") as db:
            self.assertEqual(db.execute("SELECT value FROM desktop_test_record").fetchone()[0], "preserve me")

    def test_wrong_identity_never_passes_readiness(self):
        self.start()
        with self.assertRaises(RuntimeError):
            launcher.wait_ready(self.process, "different-instance", self.url, timeout=0.2)
        self.assertIsNone(self.process.poll())

    def test_parent_pipe_close_stops_child(self):
        self.start()
        self.process.stdin.close()
        self.process.wait(timeout=10)
        self.assertEqual(self.process.returncode, 0, self.process.stdout.read().decode())


if __name__ == "__main__":
    unittest.main()
