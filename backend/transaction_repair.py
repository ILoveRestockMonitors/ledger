"""Evidence-based duplicate account repair with a quarantine, journal and undo.

The command is read-only unless --apply or --undo is supplied. Matching is a
one-to-one comparison of transaction histories on two explicitly selected bank
accounts; equal amounts inside a single account are never deduplicated.
"""
import argparse
from collections import Counter, defaultdict, deque
from datetime import date, datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import sqlite3
import uuid


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_schema(conn):
    # Individual statements preserve the caller's transaction (executescript
    # would commit an in-progress bank sync).
    conn.execute("""CREATE TABLE IF NOT EXISTS transaction_account_aliases (
        duplicate_account_id TEXT PRIMARY KEY,
        canonical_account_id TEXT NOT NULL,
        reason TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS transaction_repair_runs (
        id TEXT PRIMARY KEY, applied_at TEXT NOT NULL, undone_at TEXT,
        operations_json TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS transaction_quarantine (
        run_id TEXT NOT NULL, transaction_id TEXT NOT NULL,
        canonical_transaction_id TEXT NOT NULL, original_json TEXT NOT NULL,
        quarantined_at TEXT NOT NULL, restored_at TEXT,
        PRIMARY KEY(run_id,transaction_id)
    )""")


def aliases(conn):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='transaction_account_aliases'").fetchone():
        return {}
    return {r["duplicate_account_id"]: r["canonical_account_id"] for r in conn.execute("SELECT * FROM transaction_account_aliases")}


def _norm(value):
    return " ".join(str(value or "").casefold().split())


def account_identity(account):
    """Mask alone is deliberately insufficient to identify a real account."""
    return tuple(_norm(account.get(k)) for k in ("institution", "env", "type", "subtype", "mask", "name", "official_name"))


def transaction_key(row):
    cents = int((Decimal(str(row["amount"])) * 100).quantize(Decimal("1")))
    # Bank merchant survives a manually renamed transaction.
    merchant = _norm(row.get("merchant") or row.get("name"))
    return row["posted"], cents, merchant, int(bool(row.get("pending")))


def matching_history(source, target, minimum=5):
    """Require broad settled history and preserve repeated-charge multiplicity."""
    settled = [r for r in source if not r.get("pending")]
    if len(settled) < minimum:
        return False
    days = [date.fromisoformat(r["posted"]) for r in settled]
    if (max(days) - min(days)).days < 7:
        return False
    return not (Counter(map(transaction_key, source)) - Counter(map(transaction_key, target)))


def automatic_alias_candidate(conn, account, incoming):
    """Recognize a new duplicate feed only when all supplied history matches.

    Never guesses when two possible canonical accounts match, when there is
    insufficient history, or when the source already has stored transactions.
    Those cases stay available for an explicit audited repair.
    """
    if not account.get("mask") or not incoming:
        return None
    if conn.execute("SELECT 1 FROM transactions WHERE account_id=? LIMIT 1", (account["id"],)).fetchone():
        return None
    candidates = []
    for raw in conn.execute("""SELECT a.*,i.institution,i.env FROM accounts a JOIN items i ON i.id=a.item_id
                               WHERE a.id<>? AND a.archived=0 AND a.item_id<>?""", (account["id"], account["item_id"])):
        candidate = dict(raw)
        if account_identity(account) != account_identity(candidate):
            continue
        if candidate["id"] in aliases(conn):
            continue
        history = [dict(r) for r in conn.execute("SELECT * FROM transactions WHERE account_id=?", (candidate["id"],))]
        if matching_history(incoming, history):
            candidates.append(candidate["id"])
    return candidates[0] if len(candidates) == 1 else None


def _row(conn, table, identifier, key="id"):
    row = conn.execute(f'SELECT * FROM "{table}" WHERE "{key}"=?', (identifier,)).fetchone()
    return dict(row) if row else None


def _merged_transaction(target, source):
    result = dict(target)
    for field, flag in (("category_id", "category_override"), ("name", "name_override"),
                        ("scope", "scope_override"), ("is_transfer", "is_transfer_override")):
        source_manual = source.get(flag) is not None if flag in ("scope_override", "is_transfer_override") else source.get(flag) == 1
        target_manual = target.get(flag) is not None if flag in ("scope_override", "is_transfer_override") else target.get(flag) == 1
        if source_manual:
            if target_manual and source.get(field) != target.get(field):
                raise ValueError(f"Conflicting manual {field} on {target['id']} and {source['id']}; review before repair.")
            result[field], result[flag] = source.get(field), source.get(flag)
    if not result.get("category_id") and not result.get("category_override"):
        result["category_id"] = source.get("category_id")
    if source.get("note") and source.get("note") != target.get("note"):
        result["note"] = "\n\n".join(x for x in (target.get("note"), source["note"]) if x)
    result["recurring"] = int(bool(target.get("recurring") or source.get("recurring")))
    if source.get("split_scope") is not None or source.get("split_amount") is not None:
        for field in ("split_scope", "split_amount"):
            if target.get(field) is not None and target.get(field) != source.get(field):
                raise ValueError(f"Conflicting manual split on {target['id']}; review before repair.")
            result[field] = source.get(field)
    return result


def _transaction_references(conn):
    references = []
    for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        table = row[0]
        for fk in conn.execute(f'PRAGMA foreign_key_list("{table}")'):
            if fk[2] == "transactions":
                columns = list(conn.execute(f'PRAGMA table_info("{table}")'))
                if not any(col[1] == "id" and col[5] for col in columns):
                    raise ValueError(f"Cannot safely journal dependent table {table}; review its primary key.")
                references.append((table, fk[3]))
    return references


def plan_repair(conn, duplicate_account_id, canonical_account_id):
    if duplicate_account_id == canonical_account_id:
        raise ValueError("Select two distinct accounts.")
    accounts = {}
    for identifier in (duplicate_account_id, canonical_account_id):
        row = conn.execute("SELECT a.*,i.institution,i.env FROM accounts a JOIN items i ON i.id=a.item_id WHERE a.id=?", (identifier,)).fetchone()
        if not row:
            raise ValueError("Selected linked account not found.")
        accounts[identifier] = dict(row)
    source, target = accounts[duplicate_account_id], accounts[canonical_account_id]
    if not source.get("mask") or account_identity(source) != account_identity(target):
        raise ValueError("The accounts do not have matching bank metadata; automatic repair refused.")
    if target.get("archived") or canonical_account_id in aliases(conn):
        raise ValueError("The canonical account must be active and not an alias.")
    previous_alias = aliases(conn).get(duplicate_account_id)
    if previous_alias and previous_alias != canonical_account_id:
        raise ValueError("This account is already aliased to a different account.")
    duplicate_rows = [dict(r) for r in conn.execute("SELECT * FROM transactions WHERE account_id=? ORDER BY created_at,id", (duplicate_account_id,))]
    canonical_rows = [dict(r) for r in conn.execute("SELECT * FROM transactions WHERE account_id=? ORDER BY created_at,id", (canonical_account_id,))]
    if previous_alias and not duplicate_rows:
        return {"already_repaired": True, "operations": [], "pairs": [], "summary": {"quarantined": 0, "manual_records_preserved": 0, "scope_corrected": 0}}
    if not matching_history(duplicate_rows, canonical_rows):
        raise ValueError("The complete duplicate history is not a one-to-one subset of the canonical account; automatic repair refused.")
    grouped = defaultdict(deque)
    for row in canonical_rows:
        grouped[transaction_key(row)].append(row)
    operations, pairs = [], []
    references = _transaction_references(conn)
    manual_count = 0

    def add(table, before, after, key="id"):
        if before != after:
            operations.append({"table": table, "key": key, "id": (before or after)[key], "before": before, "after": after})

    for duplicate in duplicate_rows:
        canonical = grouped[transaction_key(duplicate)].popleft()
        merged = _merged_transaction(canonical, duplicate)
        if merged != canonical:
            manual_count += 1
        add("transactions", canonical, merged)
        for table, column in references:
            for raw in conn.execute(f'SELECT * FROM "{table}" WHERE "{column}"=?', (duplicate["id"],)):
                before = dict(raw)
                after = {**before, column: canonical["id"]}
                add(table, before, after)
        add("transactions", duplicate, None)
        pairs.append({"duplicate": duplicate["id"], "canonical": canonical["id"]})
    before = _row(conn, "accounts", duplicate_account_id)
    add("accounts", before, {**before, "archived": 1, "scope": target["scope"]})
    if not previous_alias:
        add("transaction_account_aliases", None, {"duplicate_account_id": duplicate_account_id,
            "canonical_account_id": canonical_account_id, "reason": "Verified one-to-one duplicate account history", "created_at": now()}, "duplicate_account_id")
    return {"already_repaired": False, "operations": operations, "pairs": pairs,
            "summary": {"quarantined": len(pairs), "manual_records_preserved": manual_count,
                        "scope_corrected": sum(r["scope"] != target["scope"] and r.get("scope_override") is None for r in duplicate_rows)}}


def _write_row(conn, operation, value):
    table, key, identifier = operation["table"], operation["key"], operation["id"]
    if value is None:
        conn.execute(f'DELETE FROM "{table}" WHERE "{key}"=?', (identifier,))
    elif _row(conn, table, identifier, key) is None:
        fields = list(value)
        columns = ",".join(f'"{k}"' for k in fields)
        conn.execute(f'INSERT INTO "{table}" ({columns}) VALUES ({",".join("?" for _ in fields)})', [value[k] for k in fields])
    else:
        fields = [k for k in value if k != key]
        assignments = ",".join(f'"{k}"=?' for k in fields)
        conn.execute(f'UPDATE "{table}" SET {assignments} WHERE "{key}"=?', [value[k] for k in fields] + [identifier])


def apply_plan(conn, plan):
    if plan["already_repaired"]:
        return None
    init_schema(conn)
    run_id = "repair_" + uuid.uuid4().hex[:16]
    timestamp = now()
    pair_map = {p["duplicate"]: p["canonical"] for p in plan["pairs"]}
    for op in plan["operations"]:
        if _row(conn, op["table"], op["id"], op["key"]) != op["before"]:
            raise ValueError("Data changed since this repair was planned; create a fresh plan.")
        if op["table"] == "transactions" and op["after"] is None:
            conn.execute("INSERT INTO transaction_quarantine VALUES(?,?,?,?,?,NULL)",
                         (run_id, op["id"], pair_map[op["id"]], json.dumps(op["before"]), timestamp))
        _write_row(conn, op, op["after"])
    conn.execute("INSERT INTO transaction_repair_runs(id,applied_at,operations_json) VALUES(?,?,?)",
                 (run_id, timestamp, json.dumps(plan["operations"])))
    return run_id


def merge_pending_replacement(conn, pending_id, posted_id):
    """Preserve an already-stored pending row's annotations and dependent rows.

    Only the provider's explicit pending_transaction_id may call this; date or
    amount similarities never trigger a pending merge.
    """
    pending = _row(conn, "transactions", pending_id)
    posted = _row(conn, "transactions", posted_id)
    if not pending or not posted or pending["account_id"] != posted["account_id"]:
        raise ValueError("Pending replacement must belong to the same account.")
    operations = []
    merged = _merged_transaction(posted, pending)
    if merged != posted:
        operations.append({"table": "transactions", "key": "id", "id": posted_id, "before": posted, "after": merged})
    for table, column in _transaction_references(conn):
        for row in conn.execute(f'SELECT * FROM "{table}" WHERE "{column}"=?', (pending_id,)):
            before = dict(row)
            operations.append({"table": table, "key": "id", "id": row["id"], "before": before,
                               "after": {**before, column: posted_id}})
    operations.append({"table": "transactions", "key": "id", "id": pending_id, "before": pending, "after": None})
    return apply_plan(conn, {"already_repaired": False, "operations": operations,
                             "pairs": [{"duplicate": pending_id, "canonical": posted_id}]})


def undo_run(conn, run_id):
    run = _row(conn, "transaction_repair_runs", run_id)
    if not run or run["undone_at"]:
        raise ValueError("Repair is absent or already undone.")
    operations = json.loads(run["operations_json"])
    for op in operations:
        if _row(conn, op["table"], op["id"], op["key"]) != op["after"]:
            raise ValueError("A repaired record has changed; automatic undo refused to protect newer work.")
    # Reversing restores duplicate transaction rows before their foreign keys.
    for op in reversed(operations):
        _write_row(conn, op, op["before"])
    conn.execute("UPDATE transaction_repair_runs SET undone_at=? WHERE id=?", (now(), run_id))
    conn.execute("UPDATE transaction_quarantine SET restored_at=? WHERE run_id=?", (now(), run_id))


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
            folder = Path(args.backup_dir or database.parent / "transaction-repair-backups")
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            backup = folder / ("ledger-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8] + ".sqlite3")
            with sqlite3.connect(backup) as backup_conn:
                conn.backup(backup_conn)
            os.chmod(backup, 0o600)
            conn.execute("BEGIN IMMEDIATE")
        if args.undo:
            undo_run(conn, args.undo)
            output = {"undone": args.undo, "backup": str(backup)}
        else:
            plan = plan_repair(conn, args.duplicate_account, args.canonical_account)
            output = {"dry_run": not args.apply, "already_repaired": plan["already_repaired"], **plan["summary"]}
            if args.apply:
                output.update(run_id=apply_plan(conn, plan), backup=str(backup))
        if mutating:
            violations = conn.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
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
