"""Install the self-contained Ledger desktop package for the current user."""
from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

try:
    from .win_ui import confirm, message
except ImportError:  # direct execution by the bundled runtime
    from win_ui import confirm, message


ROOT_FILES = {
    "ledger.ico", "READ-ME.txt",
    "RUNTIME-PROVENANCE.txt", "runtime-provenance.txt",
}
PRIVATE_NAMES = {"data", "Ledger-data", "backups", "node_modules", "__pycache__", ".codex"}
PRIVATE_SUFFIXES = (".db", ".db-wal", ".db-shm", ".jsonl", ".tar", ".tar.gz", ".tar.gz.enc")


class InstallError(RuntimeError):
    pass


def local_app_data() -> Path:
    value = os.environ.get("LOCALAPPDATA")
    if value:
        return Path(value).expanduser().resolve()
    if os.name == "nt":
        raise InstallError("Windows did not provide a LOCALAPPDATA folder.")
    return (Path.home() / "AppData" / "Local").resolve()


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _private(relative: Path) -> bool:
    if any(part in PRIVATE_NAMES for part in relative.parts):
        return True
    name = relative.name.lower()
    return name in {"config.json", ".env"} or name.startswith(".env.") or name.endswith(PRIVATE_SUFFIXES)


def _copy_tree(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=False)
    for current, dirs, files in os.walk(source, topdown=True, followlinks=False):
        current_path = Path(current)
        relative = current_path.relative_to(source)
        dirs[:] = [name for name in dirs if not (current_path / name).is_symlink() and not _private(relative / name)]
        for name in files:
            source_path = current_path / name
            rel = relative / name
            if source_path.is_symlink() or _private(rel):
                continue
            destination = target / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, destination)


def _copy_package(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise InstallError(f"Package folder not found: {source}")
    required = [
        source / "runtime" / "python.exe", source / "runtime" / "pythonw.exe",
        source / "runtime" / "python313.zip",
        source / "app" / "backend" / "server.py", source / "app" / "web" / "index.html",
        source / "desktop" / "windows" / "launcher.py", source / "desktop" / "windows" / "server_host.py",
        source / "ledger.ico",
    ]
    missing = [os.fspath(path.relative_to(source)) for path in required if not path.is_file()]
    if missing:
        raise InstallError("This Ledger package is incomplete: " + ", ".join(missing))
    for name in ("runtime", "app", "desktop"):
        if not (source / name).is_dir():
            raise InstallError(f"This Ledger package is missing {name}/.")
    # ``destination`` is a fresh staging directory created by install().
    for name in ("runtime", "app", "desktop"):
        _copy_tree(source / name, destination / name)
    if not (destination / "runtime" / "python313.zip").is_file():
        raise InstallError("The embedded Python standard-library archive was not copied.")
    for name in ROOT_FILES:
        path = source / name
        if path.is_file() and not path.is_symlink():
            shutil.copy2(path, destination / name)


def _ps_quote(value: str | os.PathLike[str]) -> str:
    return "'" + os.fspath(value).replace("'", "''") + "'"


def _shortcut_script(version: Path) -> str:
    pythonw = version / "runtime" / "pythonw.exe"
    launcher = version / "desktop" / "windows" / "launcher.py"
    icon = version / "ledger.ico"
    stamp = uuid.uuid4().hex
    lines = [
        "$ErrorActionPreference = 'Stop'",
        "$shell = New-Object -ComObject WScript.Shell",
        f"$pythonw = {_ps_quote(pythonw)}",
        f"$launcher = {_ps_quote(launcher)}",
        f"$icon = {_ps_quote(icon)}",
        "$desktop = [Environment]::GetFolderPath('Desktop')",
        "$programs = [Environment]::GetFolderPath('Programs')",
        "$folders = @($desktop, (Join-Path $programs 'Ledger'))",
        "$items = @(@('Ledger.lnk', ''), @('Stop Ledger.lnk', ' --stop'))",
        "foreach ($folder in $folders) {",
        "  New-Item -ItemType Directory -Force -Path $folder | Out-Null",
        "  foreach ($item in $items) {",
        "    $destination = Join-Path $folder $item[0]",
        f"    $temporary = $destination + '.tmp-{stamp}.lnk'",
        "    $link = $shell.CreateShortcut($temporary)",
        "    $link.TargetPath = $pythonw",
        "    $link.Arguments = ('\"' + $launcher + '\"' + $item[1])",
        "    $link.WorkingDirectory = Split-Path -Parent $launcher",
        "    $link.WindowStyle = 7",
        "    $link.Description = 'Ledger private finance dashboard'",
        "    $link.IconLocation = $icon + ',0'",
        "    $link.Save()",
        "    Move-Item -LiteralPath $temporary -Destination $destination -Force",
        "  }",
        "}",
    ]
    return "\n".join(lines)


def _write_shortcuts(version: Path) -> None:
    if os.name != "nt":
        return
    # Resolve the shell's redirected Desktop/Start Menu locations rather than
    # guessing from USERPROFILE (OneDrive commonly redirects Desktop).
    script = _shortcut_script(version)
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        capture_output=True, text=True, check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout or "PowerShell could not create shortcuts.").strip()
        raise InstallError(detail[:500])


def install(source: str | os.PathLike[str] | None = None) -> Path:
    source_path = Path(source or Path(__file__).resolve().parents[2]).expanduser().resolve()
    install_root = local_app_data() / "Programs" / "LedgerDesktop"
    if _is_within(source_path, install_root):
        raise InstallError("Run the installer from the supplied package folder, outside its installed versions.")
    versions = install_root / "versions"
    versions.mkdir(parents=True, exist_ok=True)
    name = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    final = versions / name
    staging = Path(tempfile.mkdtemp(prefix=".ledger-install-", dir=os.fspath(versions)))
    try:
        _copy_package(source_path, staging)
        os.replace(staging, final)
        staging = None
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)
    _write_shortcuts(final)
    return final


def _launch(version: Path) -> None:
    subprocess.Popen(
            [os.fspath(version / "runtime" / "pythonw.exe"), os.fspath(version / "desktop" / "windows" / "launcher.py")],
        cwd=os.fspath(version), close_fds=True,
    )


def main(argv: list[str] | None = None) -> int:
    try:
        source = argv[0] if argv else None
        version = install(source)
        if confirm(f"Ledger was installed for this Windows account.\n\nOpen Ledger now?", default_yes=True):
            _launch(version)
        else:
            message("Ledger is installed. Use the Ledger shortcut when you are ready.")
        return 0
    except Exception as exc:
        message("Ledger could not be installed.\n\n" + str(exc), error=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
