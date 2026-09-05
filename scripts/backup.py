#!/usr/bin/env python3
"""Encrypted, SQLite-safe Ledger backups and checked restores.

The archive is encrypted with the system ``openssl`` command through an argv
list (never a shell and never a password in argv).  SQLite's online backup API
captures a consistent database while Ledger is running.  Restore stages and
integrity-checks a copy before replacing anything, retaining a dated recovery
copy of the previous data.
"""

import argparse
import getpass
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "backend" / "data"
DEFAULT_MOUNT_ENV = "LEDGER_BACKUP_MOUNT"
PASSPHRASE_FILE_ENV = "LEDGER_BACKUP_PASSPHRASE_FILE"


def _now_name():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _data_dir(value=None):
    return Path(value or os.environ.get("LEDGER_DATA_DIR") or DEFAULT_DATA_DIR).expanduser().resolve()


def _passphrase(fd=None):
    if fd is not None:
        with os.fdopen(os.dup(fd), "rb") as stream:
            data = stream.read()
        return data.rstrip(b"\r\n")
    path = os.environ.get(PASSPHRASE_FILE_ENV)
    if path:
        return Path(path).read_bytes().rstrip(b"\r\n")
    if not sys.stdin.isatty():
        raise ValueError("passphrase required via --passphrase-fd or " + PASSPHRASE_FILE_ENV)
    return getpass.getpass("Ledger backup passphrase: ").encode("utf-8")


def _openssl(input_path, output_path, passphrase, decrypt=False):
    if not passphrase:
        raise ValueError("backup passphrase cannot be empty")
    args = ["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "600000", "-salt",
            "-pass", "stdin", "-in", os.fspath(input_path)]
    if decrypt:
        args.append("-d")
    args += ["-out", os.fspath(output_path)]
    try:
        result = subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                check=False, input=passphrase)
    except OSError as exc:
        raise RuntimeError("openssl is required for encrypted backups") from exc
    if result.returncode:
        raise ValueError("openssl could not process the backup (wrong passphrase or corrupt file)")


def _safe_member(name):
    p = Path(name)
    return not p.is_absolute() and ".." not in p.parts and name in {"ledger.db", "config.json"}


def _snapshot_database(data_dir, target):
    source_path = data_dir / "ledger.db"
    if not source_path.exists():
        raise FileNotFoundError(f"Ledger database not found: {source_path}")
    source = sqlite3.connect(source_path)
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
        result = destination.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise ValueError("database integrity check failed during snapshot")
        destination.commit()
    finally:
        destination.close()
        source.close()


def _archive(data_dir, archive_path):
    with tempfile.TemporaryDirectory(prefix="ledger-backup-") as tmp:
        db_snapshot = Path(tmp) / "ledger.db"
        _snapshot_database(data_dir, db_snapshot)
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(db_snapshot, arcname="ledger.db", recursive=False)
            config = data_dir / "config.json"
            if config.is_file() and not config.is_symlink():
                archive.add(config, arcname="config.json", recursive=False)


def backup(data_dir=None, destination=None, passphrase_fd=None, dry_run=False, allow_local=False):
    """Create ``ledger-<UTC>.tar.gz.enc`` and return its path."""
    data = _data_dir(data_dir)
    destination_value = destination or os.environ.get(DEFAULT_MOUNT_ENV)
    if not destination_value:
        raise ValueError("set --destination or " + DEFAULT_MOUNT_ENV + " to an external backup mount")
    dest = Path(destination_value).expanduser().resolve()
    if not dest.is_dir():
        raise ValueError(f"backup destination is not a directory: {dest}")
    stem = f"ledger-{_now_name()}"
    out = dest / f"{stem}.tar.gz.enc"
    suffix = 1
    while out.exists():
        out = dest / f"{stem}-{suffix}.tar.gz.enc"
        suffix += 1
    if dry_run:
        return {"path": str(out), "data_dir": str(data), "encrypted": True, "dry_run": True}
    if not allow_local and not os.path.ismount(dest):
        raise ValueError(f"{dest} is not mounted; refusing to place an external backup on local storage")
    phrase = _passphrase(passphrase_fd)
    encrypted = None
    with tempfile.TemporaryDirectory(prefix="ledger-backup-work-") as tmp:
        plain = Path(tmp) / "ledger.tar.gz"
        # The final rename must remain on the external filesystem. A /tmp
        # staging file would fail with EXDEV when the mount is separate.
        fd, encrypted_name = tempfile.mkstemp(prefix=".ledger-", suffix=".tmp", dir=dest)
        os.close(fd)
        encrypted = Path(encrypted_name)
        os.chmod(encrypted, 0o600)
        try:
            _archive(data, plain)
            _openssl(plain, encrypted, phrase)
            os.replace(encrypted, out)
            encrypted = None
        finally:
            if encrypted is not None:
                encrypted.unlink(missing_ok=True)
    os.chmod(out, 0o600)
    return {"path": str(out), "bytes": out.stat().st_size, "encrypted": True}


def _extract_archive(archive_path, staging):
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        if not members or any(not _safe_member(m.name) or not m.isfile() for m in members):
            raise ValueError("backup archive contains unexpected paths")
        names = [m.name for m in members]
        if len(names) != len(set(names)):
            raise ValueError("backup archive contains duplicate paths")
        if "ledger.db" not in names:
            raise ValueError("backup archive does not contain ledger.db")
        # Every member is a regular file with one of two exact names. Avoid
        # extractall's version-dependent filter API and never follow links.
        for member in members:
            archive.extract(member, staging)
    db_path = staging / "ledger.db"
    check = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        result = check.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise ValueError("backup database failed integrity check")
    finally:
        check.close()


def restore(backup_path, data_dir=None, passphrase_fd=None, dry_run=False):
    """Decrypt, validate, and atomically restore a backup into ``data_dir``."""
    source = Path(backup_path).expanduser().resolve()
    data = _data_dir(data_dir)
    if not source.is_file():
        raise FileNotFoundError(source)
    if dry_run:
        return {"path": str(source), "data_dir": str(data), "checked": False, "dry_run": True}
    phrase = _passphrase(passphrase_fd)
    data.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(data, 0o700)
    with tempfile.TemporaryDirectory(prefix="ledger-restore-") as tmp:
        tmpdir = Path(tmp)
        plain = tmpdir / "ledger.tar.gz"
        _openssl(source, plain, phrase, decrypt=True)
        # Keep the staged files on the same filesystem as data so replacement
        # remains atomic for an external data directory.
        staging = Path(tempfile.mkdtemp(prefix=".ledger-restore-", dir=data))
        try:
            _extract_archive(plain, staging)
            recovery = data / ("pre-restore-" + _now_name())
            while recovery.exists():
                recovery = data / ("pre-restore-" + _now_name() + "-" + uuid.uuid4().hex[:6])
            recovery.mkdir(mode=0o700)
            current_db = data / "ledger.db"
            if current_db.exists():
                # SQLite's backup API folds an existing WAL into a coherent
                # recovery database before the raw files are moved aside.
                _snapshot_database(data, recovery / "ledger.db")
            for name in ("ledger.db", "ledger.db-wal", "ledger.db-shm"):
                current = data / name
                if current.exists():
                    os.replace(current, recovery / ("current-" + name))
            config = data / "config.json"
            if config.exists():
                shutil.copy2(config, recovery / "config.json")
            for name in ("ledger.db", "config.json"):
                replacement = staging / name
                if replacement.exists():
                    os.replace(replacement, data / name)
                    os.chmod(data / name, 0o600)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    return {"restored": str(source), "data_dir": str(data), "checked": True,
            "recovery_dir": str(recovery)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--data-dir")
    common.add_argument("--passphrase-fd", type=int, help="read passphrase from an already-open file descriptor")
    common.add_argument("--dry-run", action="store_true")
    p_backup = sub.add_parser("backup", parents=[common])
    p_backup.add_argument("--destination", help="external mount directory; otherwise LEDGER_BACKUP_MOUNT")
    p_backup.add_argument("--allow-local-destination", action="store_true", help="permit an explicitly supplied local test directory")
    p_restore = sub.add_parser("restore", parents=[common])
    p_restore.add_argument("backup_path")
    args = parser.parse_args(argv)
    try:
        if args.command == "backup":
            result = backup(args.data_dir, args.destination, args.passphrase_fd, args.dry_run, args.allow_local_destination)
        else:
            result = restore(args.backup_path, args.data_dir, args.passphrase_fd, args.dry_run)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"backup: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
