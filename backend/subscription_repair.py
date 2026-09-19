"""Reconcile recurring records left behind by a verified account-alias repair.

Dry-run is the default. A matching price alone is never duplicate evidence:
each pair needs an account alias, matching billing decisions and at least two
distinct posted charges in the transaction quarantine mapped to live records.
The full original subscriptions and every changed review are retained for undo.
"""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import sqlite3
import uuid

import transaction_repair as transaction_history


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _norm(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _cents(amount):
    return int((Decimal(str(amount)) * 100).quantize(Decimal("1")))


def _table_exists(conn, table):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def init_schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS subscription_repair_runs (
        id TEXT PRIMARY KEY, applied_at TEXT NOT NULL, undone_at TEXT,
        operations_json TEXT NOT NULL, evidence_json TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS subscription_quarantine (
        run_id TEXT NOT NULL, subscription_id TEXT NOT NULL,
        canonical_subscription_id TEXT NOT NULL, original_json TEXT NOT NULL,
        quarantined_at TEXT NOT NULL, restored_at TEXT,
        PRIMARY KEY(run_id,subscription_id)
    )""")


def _evidence(conn, duplicate, canonical):
    matches = {}
    if not _table_exists(conn, "transaction_quarantine"):
        return []
    for row in conn.execute("SELECT transaction_id,canonical_transaction_id,original_json FROM transaction_quarantine WHERE restored_at IS NULL"):
        old = json.loads(row["original_json"])
        if old.get("account_id") != duplicate["account_id"] or old.get("pending") or old["amount"] >= 0:
            continue
        if _norm(old.get("merchant") or old.get("name")) != _norm(duplicate["merchant"]):
            continue
        current = transaction_history._row(conn, "transactions", row["canonical_transaction_id"])
        if not current or current.get("account_id") != canonical["account_id"] or current.get("pending"):
            continue
        if current["posted"] != old["posted"] or _cents(current["amount"]) != _cents(old["amount"]):
            continue
        if _norm(current.get("merchant") or current.get("name")) != _norm(canonical["merchant"]):
            continue
        matches[row["canonical_transaction_id"]] = {
            "duplicate_transaction_id": row["transaction_id"], "canonical_transaction_id": row["canonical_transaction_id"],
            "posted": old["posted"], "amount": old["amount"],
        }
    evidence = sorted(matches.values(), key=lambda r: (r["posted"], r["canonical_transaction_id"]))
    if len({r["posted"] for r in evidence}) < 2:
        return []
    if duplicate.get("last_seen") != canonical.get("last_seen") or duplicate.get("last_seen") != evidence[-1]["posted"]:
        return []
    return evidence


def _compatible(source, target):
    if _norm(source["merchant"]) != _norm(target["merchant"]) or _cents(source["amount"]) != _cents(target["amount"]):
        return False
    # Keep every manual billing, lifecycle and price-review choice intact.
    fields = ("cadence", "custom_interval_days", "billing_day", "next_due", "status", "management_url", "billing_channel",
              "notes", "observed_amount", "price_review", "ignored_price")
    return all(source.get(field) == target.get(field) for field in fields)


def plan(conn, duplicate_account_id, canonical_account_id):
    if transaction_history.aliases(conn).get(duplicate_account_id) != canonical_account_id:
        raise ValueError("A previously verified duplicate-account alias is required.")
    if conn.execute("SELECT 1 FROM transactions WHERE account_id=? LIMIT 1", (duplicate_account_id,)).fetchone():
        raise ValueError("Repair the duplicate transaction history before reconciling subscriptions.")
    account = transaction_history._row(conn, "accounts", canonical_account_id)
    if not account or account.get("archived"):
        raise ValueError("The canonical account must still be active.")
    duplicates = [dict(r) for r in conn.execute("SELECT * FROM subscriptions WHERE account_id=? ORDER BY id", (duplicate_account_id,))]
    targets = [dict(r) for r in conn.execute("SELECT * FROM subscriptions WHERE account_id=? ORDER BY id", (canonical_account_id,))]
    operations, pairs = [], []
    used = set()
    for duplicate in duplicates:
        matches = [(target, _evidence(conn, duplicate, target)) for target in targets
                   if target["id"] not in used and target["scope"] == account["scope"] and _compatible(duplicate, target)]
        matches = [(target, evidence) for target, evidence in matches if evidence]
        if len(matches) != 1:
            raise ValueError(f"Subscription {duplicate['id']} lacks one unambiguous match with identical billing choices and quarantined charge evidence.")
        target, evidence = matches[0]
        if _table_exists(conn, "cancellation_jobs"):
            if conn.execute("SELECT 1 FROM cancellation_jobs WHERE subscription_id=? OR (subscription_id=? AND status IN ('queued','running','needs_user')) LIMIT 1", (duplicate["id"], target["id"])).fetchone():
                raise ValueError("A related cancellation record needs separate review; no cancellation records were changed.")
        # Different learning choices could represent a deliberate lifecycle
        # decision. Do not choose which one to overwrite during a data repair.
        learn_source = transaction_history._row(conn, "subscription_learning", duplicate["normalized_key"], "normalized_key")
        learn_target = transaction_history._row(conn, "subscription_learning", target["normalized_key"], "normalized_key")
        if learn_source and learn_target and learn_source["decision"] != learn_target["decision"]:
            raise ValueError("Conflicting recurring-payment learning decisions need review.")
        # Both original learning keys remain in the DB and in the evidence
        # journal; reviews are reparented, never discarded by a cascade.
        reviews = []
        for row in conn.execute("SELECT * FROM subscription_reviews WHERE subscription_id=? ORDER BY id", (duplicate["id"],)):
            before = dict(row)
            reviews.append(before)
            operations.append({"table": "subscription_reviews", "key": "id", "id": before["id"], "before": before,
                               "after": {**before, "subscription_id": target["id"]}})
        operations.append({"table": "subscriptions", "key": "id", "id": duplicate["id"], "before": duplicate, "after": None})
        pairs.append({"duplicate_subscription_id": duplicate["id"], "canonical_subscription_id": target["id"], "merchant": duplicate["merchant"],
                      "amount": duplicate["amount"], "cadence": duplicate["cadence"], "charge_evidence": evidence, "reviews": reviews,
                      "duplicate_learning": learn_source, "canonical_learning": learn_target, "canonical_before": target})
        used.add(target["id"])
    monthly = 0
    for pair in pairs:
        row = next(r for r in duplicates if r["id"] == pair["duplicate_subscription_id"])
        if row["status"] in ("active", "cancel_requested"):
            periods = {"weekly": 52.1775, "biweekly": 26.08875, "monthly": 12, "quarterly": 4, "semiannual": 2, "annual": 1}
            annual = row["amount"] * (365.25 / row["custom_interval_days"] if row["cadence"] == "custom" else periods[row["cadence"]])
            monthly += annual / 12
    return {"operations": operations, "pairs": pairs, "summary": {"duplicate_subscriptions": len(pairs),
            "reviews_preserved": sum(len(p["reviews"]) for p in pairs), "learning_rows_changed": 0,
            "cancellation_records_changed": 0, "monthly_overstatement_removed": round(monthly, 2)}}


def apply(conn, repair_plan):
    if not repair_plan["pairs"]:
        return None
    init_schema(conn)
    # Validate every row before the first mutation.
    for operation in repair_plan["operations"]:
        if transaction_history._row(conn, operation["table"], operation["id"], operation["key"]) != operation["before"]:
            raise ValueError("Data changed after planning; create a fresh repair plan.")
    for pair in repair_plan["pairs"]:
        if transaction_history._row(conn, "subscriptions", pair["canonical_subscription_id"]) != pair["canonical_before"]:
            raise ValueError("Canonical subscription changed after planning.")
    run_id, timestamp = "subrepair_" + uuid.uuid4().hex[:16], _now()
    pairs = {p["duplicate_subscription_id"]: p for p in repair_plan["pairs"]}
    for operation in repair_plan["operations"]:
        if operation["table"] == "subscriptions" and operation["after"] is None:
            conn.execute("INSERT INTO subscription_quarantine VALUES(?,?,?,?,?,NULL)",
                         (run_id, operation["id"], pairs[operation["id"]]["canonical_subscription_id"], json.dumps(operation["before"]), timestamp))
        transaction_history._write_row(conn, operation, operation["after"])
    conn.execute("INSERT INTO subscription_repair_runs(id,applied_at,operations_json,evidence_json) VALUES(?,?,?,?)",
                 (run_id, timestamp, json.dumps(repair_plan["operations"]), json.dumps(repair_plan["pairs"])))
    return run_id


def undo(conn, run_id):
    run = transaction_history._row(conn, "subscription_repair_runs", run_id)
    if not run or run["undone_at"]:
        raise ValueError("Subscription repair is absent or already undone.")
    operations = json.loads(run["operations_json"])
    for operation in operations:
        if transaction_history._row(conn, operation["table"], operation["id"], operation["key"]) != operation["after"]:
            raise ValueError("A repaired record has newer changes; automatic undo refused.")
    for operation in reversed(operations):
        transaction_history._write_row(conn, operation, operation["before"])
    timestamp = _now()
    conn.execute("UPDATE subscription_repair_runs SET undone_at=? WHERE id=?", (timestamp, run_id))
    conn.execute("UPDATE subscription_quarantine SET restored_at=? WHERE run_id=?", (timestamp, run_id))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--duplicate-account")
    parser.add_argument("--canonical-account")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--undo", metavar="RUN_ID")
    parser.add_argument("--backup-dir")
    args = parser.parse_args()
    mutating = args.apply or bool(args.undo)
    database = Path(args.database).resolve()
    conn = sqlite3.connect(database.as_uri() + ("?mode=rw" if mutating else "?mode=ro"), uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        if not args.undo and (not args.duplicate_account or not args.canonical_account):
            parser.error("--duplicate-account and --canonical-account are required")
        if mutating:
            folder = Path(args.backup_dir or database.parent / "subscription-repair-backups")
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            backup = folder / ("ledger-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8] + ".sqlite3")
            with sqlite3.connect(backup) as destination:
                conn.backup(destination)
            os.chmod(backup, 0o600)
            conn.execute("BEGIN IMMEDIATE")
        if args.undo:
            undo(conn, args.undo)
            output = {"undone": args.undo, "backup": str(backup)}
        else:
            repair_plan = plan(conn, args.duplicate_account, args.canonical_account)
            output = {"dry_run": not args.apply, **repair_plan["summary"], "pairs": [
                {"duplicate": p["duplicate_subscription_id"], "canonical": p["canonical_subscription_id"], "merchant": p["merchant"],
                 "amount": p["amount"], "cadence": p["cadence"], "mapped_charges": len(p["charge_evidence"])} for p in repair_plan["pairs"]]}
            if args.apply:
                output.update(run_id=apply(conn, repair_plan), backup=str(backup))
        if mutating:
            if conn.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("Foreign-key validation failed; repair rolled back.")
            conn.commit()
        print(json.dumps(output, indent=2))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
