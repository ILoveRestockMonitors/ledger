"""Build the self-contained Windows ZIP from the vetted source-only release."""
from pathlib import Path
import argparse
import hashlib
import shutil
import tempfile
import zipfile


RUNTIME_SHA256 = "d1f04d990aee1253d8569e8e5104e30fa9f5fa830899f14843448872d936a2cf"
RUNTIME_URL = "https://www.python.org/ftp/python/3.13.15/python-3.13.15-embed-amd64.zip"
SOURCE_SHA256 = "c43ed2a57115395d06f421af7476ddd6de6293f7c0df8a83a538515650305941"

GUIDE = """LEDGER FOR WINDOWS — START HERE

Install once
1. Right-click Ledger-Desktop-Windows.zip and choose Extract All.
2. If your old Ledger command window is still running, press Ctrl+C in that
   window once to stop it before opening the desktop version.
3. Open the extracted Ledger-Desktop-Windows folder. Double-click INSTALL-LEDGER
   (the Windows Command Script). You do not have to type or paste anything.
4. When installation finishes, choose Yes to open Ledger.

After that, just double-click the Ledger icon on your desktop or in the Start menu.
The installer includes Python. No separate Python, Codex, or paid AI is needed.
The setup window may appear briefly; everyday use has no command window.

Your existing records
Ledger uses the same data folder from the previous Windows instructions:
    %LOCALAPPDATA%\\LedgerPersonal
Your records and password stay there. The installer does not copy, replace,
or delete that folder. If you previously chose a custom data location and Ledger
looks empty, stop and ask for help using that location before adding new records.
Create a password only if you have never set up Ledger before.

Opening and stopping
Ledger opens in an Edge app-style window. If Edge is unavailable it uses your
default browser. It is still the same private, local finance app.
Closing the window leaves Ledger running in the background so it can reopen
quickly. Use the Stop Ledger desktop/Start menu icon to stop it completely.
Wait for its confirmation before backing up the entire LedgerPersonal folder.
Restarting Windows stops Ledger; click Ledger to start it again afterward.

No administrator account is needed. This package targets 64-bit Intel/AMD
Windows 10 or 11. It does not install a service, start at login, or change your
existing Python. Program files live under:
    %LOCALAPPDATA%\\Programs\\LedgerDesktop\\versions
Updates install a separate program version and keep your records and older
versions. After installing an update, Stop Ledger and reopen Ledger to use it.

If something goes wrong
An occupied address usually means the old command-window version is still running.
The app will not close another program or silently switch to a different database.
Startup errors show a message. Its private local log is in LedgerPersonal\\desktop.log.
If Windows or a managed-computer policy blocks this custom unsigned package, ask
for help with that message; you should not need to disable security protections.
This package's lifecycle and data checks were run on macOS. Windows installer and
desktop-window behavior still need a first-run check on your Windows computer.

Manual spending, budgets, subscriptions, reports and projections work without AI.
Bank syncing and AI cancellation/purchase lookup still need their separate setup.
This does not connect to the sender's Codex subscription or home lab.
It contains no personal financial records, credentials or saved browser sessions.
"""


def safe_extract(archive, destination):
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            path = Path(info.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in info.filename:
                raise ValueError("Invalid archive member")
        if z.testzip() is not None:
            raise ValueError("Damaged ZIP")
        z.extractall(destination)


def build(source, runtime, output):
    if hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError("Unexpected source release. Review it and update the pinned digest first.")
    if hashlib.sha256(runtime.read_bytes()).hexdigest() != RUNTIME_SHA256:
        raise ValueError("Runtime SHA256 does not match Python.org.")
    windows = Path(__file__).resolve().parent / "windows"
    with tempfile.TemporaryDirectory(prefix="ledger-windows-build-") as temp:
        temp = Path(temp)
        root = temp / "Ledger-Desktop-Windows"
        root.mkdir()
        safe_extract(source, temp / "source")
        shutil.copytree(temp / "source" / "Ledger", root / "app")
        safe_extract(runtime, root / "runtime")
        # Isolated embedded Python needs explicit application import paths.
        (root / "runtime/python313._pth").write_text(
            "python313.zip\n.\n../desktop/windows\n../app/backend\n", encoding="utf-8")
        (root / "desktop/windows").mkdir(parents=True)
        for name in ["launcher.py", "server_host.py", "win_ui.py", "install.py"]:
            shutil.copy2(windows / name, root / "desktop/windows" / name)
        shutil.copy2(windows / "INSTALL-LEDGER.cmd", root / "INSTALL-LEDGER.cmd")
        shutil.copy2(windows / "ledger.ico", root / "ledger.ico")
        (root / "READ-ME.txt").write_text(GUIDE, encoding="utf-8")
        (root / "RUNTIME-PROVENANCE.txt").write_text(
            "CPython 3.13.15 official Windows x64 embeddable distribution\n"
            + RUNTIME_URL + "\nOriginal ZIP SHA256: " + RUNTIME_SHA256
            + "\nPython.org release: https://www.python.org/downloads/release/python-31315/\n"
            + "Runtime license: runtime/LICENSE.txt\n"
            + "Only python313._pth was changed to add application import paths.\n"
            + "Application source archive SHA256: " + SOURCE_SHA256 + "\n", encoding="utf-8")
        files = sorted(p for p in root.rglob("*") if p.is_file())
        for p in files:
            rel = p.relative_to(root)
            if "data" in rel.parts or p.name.endswith((".db", ".jsonl")) or p.name == ".env":
                raise ValueError(f"Private runtime data in package: {rel}")
        manifest = "".join(hashlib.sha256(p.read_bytes()).hexdigest() + "  "
                           + p.relative_to(root).as_posix() + "\n" for p in files)
        (root / "PACKAGE-MANIFEST.sha256").write_text(manifest, encoding="utf-8")
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(root.rglob("*")):
                if p.is_file():
                    z.write(p, p.relative_to(temp))
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".sha256").write_text(digest + "  " + output.name + "\n")
    return digest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(build(args.source, args.runtime, args.output))
