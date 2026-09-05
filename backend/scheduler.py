"""Bounded background synchronization for Ledger.

The scheduler is deliberately a small coordinator.  Plaid remains the source
of incremental pagination and cursor handling in ``plaid_client.refresh_item``;
this module serializes runs, records per-item outcomes, and triggers a
subscription scan after successful ingestion.
"""

import os
import threading
import time
from datetime import datetime, timezone

try:  # ``python backend/server.py`` puts backend/ on sys.path.
    import db
except ImportError:  # package imports used by the test suite.
    from . import db


DEFAULT_INTERVAL_MINUTES = 240
MIN_INTERVAL_MINUTES = 5
MAX_INTERVAL_MINUTES = 24 * 60

_state_lock = threading.RLock()
_run_lock = threading.Lock()
_stop_event = None
_thread = None
_state = {
    "running": False,
    "last_run_started": None,
    "last_run_finished": None,
    "last_result": None,
    "next_run": None,
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def init_schema():
    db.ex("""CREATE TABLE IF NOT EXISTS sync_state (
      item_id TEXT PRIMARY KEY,
      status TEXT NOT NULL,
      started_at TEXT,
      finished_at TEXT,
      added INTEGER NOT NULL DEFAULT 0,
      error TEXT,
      FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
    )""")
    db.ex("CREATE INDEX IF NOT EXISTS idx_sync_state_status ON sync_state(status)")


def _interval_minutes():
    raw = db.get_config().get("sync_interval_minutes", DEFAULT_INTERVAL_MINUTES)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_INTERVAL_MINUTES
    return max(MIN_INTERVAL_MINUTES, min(MAX_INTERVAL_MINUTES, value))


def _test_mode():
    return bool(os.environ.get("LEDGER_TESTING") or os.environ.get("PYTEST_CURRENT_TEST"))


def _error_message(exc):
    """Return a generic error suitable for the status API.

    Provider and test doubles can accidentally include request payloads (and
    therefore access tokens) in exception text. Keep details in local provider
    logs, if any, and expose only the exception class to the dashboard.
    """
    return f"{type(exc).__name__ or 'Error'} while syncing"


def _snapshot():
    with _state_lock:
        current = dict(_state)
    try:
        current["items"] = db.q("SELECT * FROM sync_state ORDER BY item_id")
    except Exception:
        current["items"] = []
    current["interval_minutes"] = _interval_minutes()
    current["enabled"] = _thread is not None and _thread.is_alive()
    current["test_mode"] = _test_mode()
    if current["running"]:
        current["message"] = "A bank sync is in progress."
    elif current.get("test_mode"):
        current["message"] = "Automatic bank sync is disabled in test mode."
    elif not current.get("last_run_finished"):
        current["message"] = "Automatic bank sync is ready."
    elif any(row.get("status") == "error" for row in current.get("items", [])):
        current["message"] = "Some bank connections need attention."
    else:
        current["message"] = "Bank connections are up to date."
    return current


def status():
    """Return scheduler readiness and last-known item outcomes."""
    init_schema()
    return _snapshot()


def _set_item(item_id, status, started=None, finished=None, added=0, error=None):
    db.ex("""INSERT INTO sync_state(item_id,status,started_at,finished_at,added,error)
              VALUES(?,?,?,?,?,?)
              ON CONFLICT(item_id) DO UPDATE SET status=excluded.status,
                started_at=COALESCE(excluded.started_at,sync_state.started_at),
                finished_at=excluded.finished_at, added=excluded.added,error=excluded.error""",
           (item_id, status, started, finished, added, error))


def _items():
    # Selecting only rows with access tokens ensures demo/manual records never
    # invoke a network client.  Token values are not copied into result data.
    return db.q("SELECT id FROM items WHERE access_token IS NOT NULL AND access_token <> '' ORDER BY id")


def sync_all():
    """Refresh every linked Plaid Item once and return a redacted run report.

    A concurrent caller receives a ``skipped`` result and cannot overlap a
    Plaid run. Tests that exercise orchestration patch ``_test_mode`` to false
    and replace the client; an ordinary test process never makes Plaid calls.
    """
    init_schema()
    # A test process must never reach the network even if a caller invokes the
    # public sync seam directly. Tests that exercise orchestration patch
    # ``_test_mode`` to False and replace ``plaid_client.refresh_item``.
    if _test_mode():
        return {"status": "skipped", "reason": "test mode", "message": "Automatic bank sync is disabled in test mode.", "items": []}
    if not _run_lock.acquire(blocking=False):
        return {"status": "skipped", "reason": "run already in progress", "message": "A bank sync is already in progress.", "items": []}
    started = _now()
    with _state_lock:
        _state.update({"running": True, "last_run_started": started, "last_result": None})
    results = []
    successes = 0
    try:
        try:
            from . import plaid_client
        except ImportError:  # ``python backend/server.py`` entry point.
            import plaid_client
        items = _items()
        for item in items:
            item_id = item["id"]
            item_started = _now()
            _set_item(item_id, "running", started=item_started, finished=None, added=0, error=None)
            try:
                value = plaid_client.refresh_item(item_id)
                added = int((value or {}).get("added", 0)) if isinstance(value, dict) else 0
                item_finished = _now()
                _set_item(item_id, "ok", finished=item_finished, added=added, error=None)
                results.append({"item_id": item_id, "status": "ok", "added": added})
                successes += 1
            except Exception as exc:  # Plaid errors must not stop other Items.
                item_finished = _now()
                message = _error_message(exc)
                _set_item(item_id, "error", finished=item_finished, added=0, error=message)
                results.append({"item_id": item_id, "status": "error", "error": message})

        scan = None
        if successes:
            try:
                try:
                    from . import subscriptions
                except ImportError:  # ``python backend/server.py`` entry point.
                    import subscriptions
                scan = subscriptions.scan()
            except Exception as exc:  # Scan failure is visible but sync remains valid.
                scan = {"status": "error", "error": _error_message(exc)}
        failed = sum(1 for row in results if row["status"] == "error")
        outcome = {"status": "ok", "message": "Some bank connections need attention." if failed else "Bank connections are up to date.",
                   "started_at": started, "finished_at": _now(), "items": results,
                   "subscription_scan": scan}
        with _state_lock:
            _state["last_result"] = outcome
        return outcome
    finally:
        finished = _now()
        with _state_lock:
            _state.update({"running": False, "last_run_finished": finished})
        _run_lock.release()


def _worker(stop):
    interval = _interval_minutes() * 60
    while not stop.is_set():
        # Test-mode workers are inert, while production workers run once per
        # interval. A run-level failure must not permanently kill the worker.
        if not _test_mode():
            try:
                sync_all()
            except Exception as exc:
                with _state_lock:
                    _state.update({
                        "running": False,
                        "last_run_finished": _now(),
                        "last_result": {
                            "status": "error",
                            "message": "Automatic bank sync failed.",
                            "items": [],
                            "error": _error_message(exc),
                        },
                    })
        interval = _interval_minutes() * 60
        deadline = time.time() + interval
        with _state_lock:
            _state["next_run"] = datetime.fromtimestamp(deadline, timezone.utc).isoformat()
        if stop.wait(interval):
            return


def start():
    """Start one daemon scheduler thread; repeated calls are idempotent."""
    global _stop_event, _thread
    init_schema()
    with _state_lock:
        if _thread is not None and _thread.is_alive():
            return _stop_event
        _stop_event = threading.Event()
        _thread = threading.Thread(target=_worker, args=(_stop_event,), name="ledger-sync", daemon=True)
        _thread.start()
        return _stop_event


def stop(timeout=5):
    """Stop the scheduler thread and wait briefly for a clean exit."""
    global _stop_event, _thread
    with _state_lock:
        event, thread = _stop_event, _thread
    if event:
        event.set()
    if thread and thread is not threading.current_thread():
        thread.join(timeout=max(0, float(timeout)))
    with _state_lock:
        if _thread is thread:
            _thread = None
            _stop_event = None
            _state["next_run"] = None
