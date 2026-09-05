"""Small Windows UI and single-instance primitives for the Ledger desktop.

The application itself stays a normal localhost web server.  This module only
owns the pieces that make a double-clicked Windows package predictable: native
message boxes, opening the local app, and named kernel objects shared by the
launcher and its Stop shortcut.
"""
from __future__ import annotations

import ctypes
import hashlib
import os
import subprocess
import threading
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit


APP_TITLE = "Ledger"


def message(text: str, error: bool = False) -> None:
    """Show a visible message even when the launcher uses pythonw.exe."""
    text = str(text)
    if os.name != "nt":
        print(f"{APP_TITLE}: {text}")
        return
    flags = 0x00000010 if error else 0x00000040  # MB_ICONERROR / MB_ICONINFORMATION
    ctypes.windll.user32.MessageBoxW(None, text, APP_TITLE, flags)


def confirm(text: str, default_yes: bool = True) -> bool:
    """Ask a yes/no question, used only for the post-install launch offer."""
    if os.name != "nt":
        return default_yes
    flags = 0x00000004 | (0x00000000 if default_yes else 0x00000100)  # MB_YESNO + default button
    return ctypes.windll.user32.MessageBoxW(None, str(text), APP_TITLE, flags) == 6  # IDYES


def _edge_path() -> str | None:
    candidates = []
    for variable in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(variable)
        if base:
            candidates.append(Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe")
    for candidate in candidates:
        if candidate.is_file():
            return os.fspath(candidate)
    return None


def _valid_local_url(url: str) -> bool:
    try:
        parsed = urlsplit(str(url))
        return (parsed.scheme in ("http", "https") and parsed.hostname == "127.0.0.1"
                and not parsed.username and not parsed.password and bool(parsed.port))
    except ValueError:
        return False


def open_window(url: str) -> bool:
    """Open Ledger in Edge app mode, falling back to the default browser."""
    if not _valid_local_url(url):
        message("Ledger could not open an invalid application address.", error=True)
        return False
    edge = _edge_path() if os.name == "nt" else None
    if edge:
        try:
            subprocess.Popen([edge, f"--app={url}"], close_fds=True)
            return True
        except OSError:
            pass
    try:
        opened = bool(webbrowser.open(url, new=1))
    except Exception:
        opened = False
    if not opened:
        message(f"Ledger is running, but your browser could not open {url}.", error=True)
    return opened


if os.name == "nt":
    import ctypes.wintypes as wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _HANDLE = wintypes.HANDLE
    _DWORD = wintypes.DWORD
    _kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    _kernel32.CreateMutexW.restype = _HANDLE
    _kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    _kernel32.CreateEventW.restype = _HANDLE
    _kernel32.WaitForSingleObject.argtypes = [_HANDLE, _DWORD]
    _kernel32.WaitForSingleObject.restype = _DWORD
    _kernel32.WaitForMultipleObjects.argtypes = [_DWORD, ctypes.POINTER(_HANDLE), wintypes.BOOL, _DWORD]
    _kernel32.WaitForMultipleObjects.restype = _DWORD
    _kernel32.SetEvent.argtypes = [_HANDLE]
    _kernel32.SetEvent.restype = wintypes.BOOL
    _kernel32.ReleaseMutex.argtypes = [_HANDLE]
    _kernel32.ReleaseMutex.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [_HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL

    _WAIT_OBJECT_0 = 0x00000000
    _WAIT_TIMEOUT = 0x00000102
    _WAIT_FAILED = 0xFFFFFFFF
    _WAIT_ABANDONED = 0x00000080


_fallback_state_lock = threading.Lock()
_fallback_events: dict[str, dict[str, object]] = {}


class Instance:
    """Named mutex plus open/stop auto-reset events for one data directory."""

    def __init__(self, data_dir: str | os.PathLike[str]):
        resolved = os.path.normcase(os.path.realpath(os.path.abspath(os.fspath(data_dir))))
        digest = hashlib.sha256(resolved.encode("utf-8", "surrogatepass")).hexdigest()[:32]
        self._key = digest
        self._mutex = None
        self._events = None
        self._owner = False
        self._closed = False
        if os.name == "nt":
            prefix = f"Local\\LedgerDesktop-{digest}"
            self._mutex = _kernel32.CreateMutexW(None, False, prefix + "-mutex")
            if not self._mutex:
                raise ctypes.WinError(ctypes.get_last_error())
            # Create these before acquiring the mutex. A second click can
            # signal the event while the first process is still starting.
            open_event = _kernel32.CreateEventW(None, False, False, prefix + "-open")
            stop_event = _kernel32.CreateEventW(None, False, False, prefix + "-stop")
            if not open_event or not stop_event:
                if open_event:
                    _kernel32.CloseHandle(open_event)
                if stop_event:
                    _kernel32.CloseHandle(stop_event)
                _kernel32.CloseHandle(self._mutex)
                raise ctypes.WinError(ctypes.get_last_error())
            self._events = (open_event, stop_event)
        else:
            with _fallback_state_lock:
                self._events = _fallback_events.setdefault(
                    digest,
                    {"lock": threading.Lock(), "open": threading.Event(), "stop": threading.Event()},
                )

    def acquire(self) -> bool:
        if self._closed:
            return False
        if os.name != "nt":
            self._owner = self._events["lock"].acquire(blocking=False)
            return self._owner
        result = _kernel32.WaitForSingleObject(self._mutex, 0)
        if result in (_WAIT_OBJECT_0, _WAIT_ABANDONED):
            self._owner = True
            return True
        if result == _WAIT_TIMEOUT:
            return False
        raise ctypes.WinError(ctypes.get_last_error())

    def signal(self, action: str) -> bool:
        if action not in ("open", "stop") or self._closed:
            return False
        if os.name != "nt":
            self._events[action].set()
            return True
        index = 0 if action == "open" else 1
        if not _kernel32.SetEvent(self._events[index]):
            raise ctypes.WinError(ctypes.get_last_error())
        return True

    def wait(self, timeout_ms: int) -> str | None:
        if self._closed:
            return None
        timeout_ms = max(0, int(timeout_ms))
        if os.name != "nt":
            events = (self._events["open"], self._events["stop"])
            deadline = threading.Event()
            # This fallback is only for source-tree tests; Windows uses the
            # kernel wait below. Polling keeps the same auto-reset semantics.
            remaining = timeout_ms / 1000
            while True:
                for name, event in (("stop", events[1]), ("open", events[0])):
                    if event.is_set():
                        event.clear()
                        return name
                if remaining <= 0:
                    return None
                step = min(0.05, remaining)
                deadline.wait(step)
                remaining -= step
        # Prefer a stop request if both notifications arrive together.
        handles = (_HANDLE * 2)(self._events[1], self._events[0])
        result = _kernel32.WaitForMultipleObjects(2, handles, False, timeout_ms)
        if result == _WAIT_TIMEOUT:
            return None
        if result == _WAIT_FAILED:
            raise ctypes.WinError(ctypes.get_last_error())
        if result == _WAIT_OBJECT_0:
            return "stop"
        if result == _WAIT_OBJECT_0 + 1:
            return "open"
        raise ctypes.WinError(ctypes.get_last_error())

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if os.name != "nt":
            if self._owner:
                self._events["lock"].release()
            self._owner = False
            return
        if self._owner:
            _kernel32.ReleaseMutex(self._mutex)
            self._owner = False
        for handle in self._events or ():
            _kernel32.CloseHandle(handle)
        if self._mutex:
            _kernel32.CloseHandle(self._mutex)
            self._mutex = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()
