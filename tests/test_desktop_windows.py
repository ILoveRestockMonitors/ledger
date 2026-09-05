"""Portable checks for the Windows desktop package layout.

The native PowerShell, Edge, mutex, and event calls are intentionally not
exercised on this non-Windows test host. These tests cover the pure installer
rules and the fallback Instance semantics; Windows packaging still needs one
native smoke test on the target machine.
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from desktop.windows import install, win_ui


class DesktopWindowsPackageTests(unittest.TestCase):
    def _package(self, root: Path) -> Path:
        source = root / "O'Neil Ledger"
        for relative in ("runtime", "app/backend", "app/web", "desktop/windows"):
            (source / relative).mkdir(parents=True, exist_ok=True)
        for relative, value in {
            "runtime/python.exe": "python",
            "runtime/pythonw.exe": "pythonw",
            "runtime/python313.zip": "stdlib",
            "app/backend/server.py": "server",
            "app/web/index.html": "html",
            "desktop/windows/launcher.py": "launcher",
            "desktop/windows/server_host.py": "host",
            "ledger.ico": "icon",
        }.items():
            (source / relative).write_text(value, encoding="utf-8")
        # These are deliberate private-file fixtures and must never enter an
        # installed version.
        (source / "app/backend/data").mkdir()
        (source / "app/backend/data/ledger.db").write_text("private", encoding="utf-8")
        (source / "app/config.json").write_text("private", encoding="utf-8")
        return source

    def test_install_copies_runtime_zip_nested_launchers_and_preserves_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self._package(root)
            local_app_data = root / "Local AppData"
            data = local_app_data / "LedgerPersonal"
            data.mkdir(parents=True)
            sentinel = data / "ledger.db"
            sentinel.write_text("existing", encoding="utf-8")
            old_version = local_app_data / "Programs/LedgerDesktop/versions/old-version"
            old_version.mkdir(parents=True)
            (old_version / "keep.txt").write_text("keep", encoding="utf-8")

            with patch.dict(os.environ, {"LOCALAPPDATA": os.fspath(local_app_data)}, clear=False), \
                    patch.object(install, "_write_shortcuts") as write_shortcuts:
                version = install.install(source)

            self.assertTrue((version / "runtime/python313.zip").is_file())
            self.assertTrue((version / "desktop/windows/launcher.py").is_file())
            self.assertTrue((version / "desktop/windows/server_host.py").is_file())
            self.assertFalse((version / "app/backend/data").exists())
            self.assertFalse((version / "app/config.json").exists())
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "existing")
            self.assertEqual((old_version / "keep.txt").read_text(encoding="utf-8"), "keep")
            write_shortcuts.assert_called_once_with(version)

    def test_installer_rejects_source_inside_install_tree_and_quotes_unicode(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            local_app_data = root / "Local AppData"
            install_tree = local_app_data / "Programs/LedgerDesktop/versions/current"
            install_tree.mkdir(parents=True)
            with patch.dict(os.environ, {"LOCALAPPDATA": os.fspath(local_app_data)}, clear=False):
                with self.assertRaises(install.InstallError):
                    install.install(install_tree)
            quoted = install._ps_quote("C:/Users/Zoë O'Neil/Ledger")
            self.assertEqual(quoted, "'C:/Users/Zoë O''Neil/Ledger'")
            script = install._shortcut_script(Path("C:/Users/Zoë O'Neil/LedgerDesktop/versions/v"))
            self.assertIn("Zoë", script)
            self.assertIn("O''Neil", script)
            self.assertIn("GetFolderPath('Desktop')", script)
            self.assertIn("GetFolderPath('Programs')", script)

    def test_root_cmd_uses_package_root_without_delayed_expansion(self):
        command = (Path(__file__).resolve().parents[1] / "desktop/windows/INSTALL-LEDGER.cmd").read_text(encoding="utf-8")
        self.assertIn("setlocal DisableDelayedExpansion", command)
        self.assertIn("set \"PACKAGE_ROOT=%~dp0\"", command)
        self.assertIn("desktop\\windows\\install.py", command)

    @unittest.skipIf(os.name == "nt", "native named mutexes are reentrant for one thread; use separate Windows processes")
    def test_portable_instance_fallback_is_per_data_directory_and_auto_resets_events(self):
        with tempfile.TemporaryDirectory() as temporary:
            first_path, second_path = Path(temporary) / "one", Path(temporary) / "two"
            first, first_again, second = (win_ui.Instance(first_path), win_ui.Instance(first_path), win_ui.Instance(second_path))
            try:
                self.assertTrue(first.acquire())
                self.assertFalse(first_again.acquire())
                self.assertTrue(second.acquire())
                first.signal("open")
                self.assertEqual(first.wait(100), "open")
                self.assertIsNone(first.wait(0))
                first.signal("stop")
                self.assertEqual(first.wait(100), "stop")
            finally:
                first.close()
                first_again.close()
                second.close()


if __name__ == "__main__":
    unittest.main()
