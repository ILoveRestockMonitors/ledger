"""Coordinate the purchase-history worker without exposing its local files."""
import os
import threading
import time

import db
import receipt_store
import receipt_worker
import amazon_connector

_lock = threading.Lock()
_last_scan = 0.0


def disabled():
    return os.environ.get("LEDGER_DEMO") == "1" or bool(
        os.environ.get("LEDGER_TESTING") or os.environ.get("PYTEST_CURRENT_TEST")
    )


def settings():
    config = db.get_config()
    return {"enabled": bool(config.get("receipt_lookup_enabled", False)),
            "auto_apply": bool(config.get("receipt_auto_apply", True)),
            "daily_limit": config.get("receipt_daily_limit", 10)}


def save_settings(data, demo=False):
    patch = {}
    for public, stored in (("enabled", "receipt_lookup_enabled"),
                           ("auto_apply", "receipt_auto_apply")):
        if public in data:
            if not isinstance(data[public], bool):
                raise ValueError("Choose an on or off setting.")
            if public == "enabled" and data[public] and (demo or disabled()):
                raise ValueError("Purchase lookups are off in this preview. Enable them on your private Ledger after setup.")
            patch[stored] = data[public]
    if "daily_limit" in data:
        value = data["daily_limit"]
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 30:
            raise ValueError("Choose a daily lookup limit from 1 to 30.")
        patch["receipt_daily_limit"] = value
    db.save_config(patch)
    return settings()


def status(demo=False):
    if demo or disabled():
        return {"ready": False, "message": "Purchase lookups are off in this preview. Your merchant accounts are never opened here."}
    amazon = amazon_connector.status()
    return {"ready": amazon['ready'], "message": amazon['message'], "codex_required": False,
            "instructions": "Connect Amazon Business in Settings. Its charge and item matching runs directly on Ledger without Codex. Apple and Google use the separate legacy purchase worker."}


def listing(demo=False):
    result = receipt_store.listing()
    amazon = {"connected":False,"ready":False,"stage":"disconnected","message":"Amazon connection is off in sample mode."} if demo or disabled() else amazon_connector.status()
    return {**result, "settings": settings(), "worker": status(demo), "amazon":amazon, "demo": bool(demo or disabled())}


def run_once():
    """Run at most one lookup; all queue changes are owned by receipt_store."""
    global _last_scan
    if disabled() or not _lock.acquire(blocking=False):
        return None
    try:
        now = time.monotonic()
        if now - _last_scan >= 60:
            receipt_store.scan()
            _last_scan = now
        if settings()['enabled']: amazon_connector.tick()
        amazon = amazon_connector.status()
        job = receipt_store.claim_next(providers=['amazon']) if amazon['ready'] else None
        if not job: job = receipt_store.claim_next(providers=['apple','google'])
        if not job:
            return None
        try:
            result = amazon_connector.investigate(job) if job['provider'] == 'amazon' else receipt_worker.investigate(job)
        except Exception:
            # Raw provider/model failures can contain private receipt text.
            result = {"verified": False, "payload": {
                "status": "failed", "message": "The purchase lookup stopped before it could verify a receipt. You can retry from its details."
            }}
        try:
            return receipt_store.finish(job["id"], result.get("payload") or {},
                                        verified=result.get("verified") is True,
                                        expected_attempt=job.get("attempts"))
        except (ValueError, TypeError, KeyError):
            # Invalid model output must release the durable claim for retry.
            # Never copy raw payloads or exception text into the public status.
            return receipt_store.finish(job["id"], {
                "status": "failed",
                "message": "The receipt details could not be verified. Your transaction is unchanged; you can retry the lookup."
            }, verified=False, expected_attempt=job.get("attempts"))
    finally:
        _lock.release()
