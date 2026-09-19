"""Reconcile an imported manual checking history with its live bank account.

This companion deliberately requires two selected accounts, matching account
metadata, and broad posted history. Only same-day, same-signed-amount,
same-descriptor records with equal multiplicity are merged automatically.
Unmatched historical and manually entered records keep their IDs and move to
the bank account; bank dates, amounts, provider IDs and balance remain intact.
All changes use transaction_repair's quarantine, exact-state journal and undo.

Dry-run is the default. Exceptional, explicitly reviewed pairs can be supplied
as JSON; these must still have equal signed amounts and nearby posting dates.
"""
import argparse
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import sqlite3
import uuid

import transaction_repair as history


def _cents(amount):
    return int((Decimal(str(amount)) * 100).quantize(Decimal("1")))


def _norm(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def descriptor(tx):
    """Documented bank/Copilot label variants, not fuzzy merchant similarity."""
    label = _norm(tx.get("merchant") or tx.get("name"))
    if label.startswith("dep at "):
        # Copilot can repeat the ATM address; the bank can append a card mask.
        # Preserve the location itself so different ATMs do not become aliases.
        label = re.split(r"\s+dep at\s+", label, maxsplit=1)[0]
        return re.sub(r"\s+\d{4}(?: [a-z])?$", "", label)
    mappings = (
        (r"^web funds transfer from account\b", "funds transfer from account"),
        (r"^web funds transfer to account\b", "funds transfer to account"),
        (r"^amex epayment ach\b", "amex epayment ach"),
        (r"^amex epayment retry pymt\b", "amex epayment retry pymt"),
        (r"^fifth third bank (?:web )?pay\b", "fifth third bank pay"),
        (r"^schwab brokerage moneylink\b", "schwab brokerage moneylink"),
        (r"^(?:in shape|inshape)\b", "in shape"),
        (r"^upgrade(?: inc)?(?: payment| retry pymt)?$", "upgrade"),
        (r"^(?:irs usataxpymt|internal revenue service)$", "irs"),
        (r"^franchise tax bo(?: payments)?$", "franchise tax bo"),
        (r"^(?:santa cruz pay by phon\b.*|city of santa cruz(?: government building)?)$", "santa cruz parking"),
        (r"^(?:pmusa\b.*|parkmobile)$", "parkmobile"),
        (r"^paypal purchase\b", "paypal purchase"),
        (r"^paypal(?: inst xfer| transfer(?: \d+)?)?$", "paypal transfer"),
        (r"^rtp from paypal\b", "rtp from paypal"),
        (r"^(?:e )?statement discount$", "statement discount"),
        (r"^(?:mobile deposit|deposit)$", "deposit"),
        (r"^non comerica atm usage fee w d\b", "non comerica atm fee"),
    )
    return next((replacement for pattern, replacement in mappings if re.search(pattern, label)), label)


def _key(tx):
    return tx["posted"], _cents(tx["amount"]), descriptor(tx)


def _annotation(tx):
    return tuple(tx.get(k) for k in ("name", "name_override", "category_id", "category_override",
        "scope", "scope_override", "is_transfer", "is_transfer_override", "note", "recurring", "split_scope", "split_amount"))


def _add(operations, table, before, after, key="id"):
    if before != after:
        operations.append({"table": table, "key": key, "id": (before or after)[key], "before": before, "after": after})


def _move_subscription_references(conn, source, target, operations):
    """Keep unique commitments and their user decisions attached to the account."""
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    moved = []
    if "subscriptions" in tables:
        for raw in conn.execute("SELECT * FROM subscriptions WHERE account_id=?", (source["id"],)):
            old = dict(raw)
            scope = "business" if target["scope"] == "business" else old["scope"]
            new_key = (_norm(old["merchant"]) or "unknown merchant") + "|" + scope + "|" + target["id"]
            if conn.execute("SELECT id FROM subscriptions WHERE normalized_key=? AND id<>?", (new_key, old["id"])).fetchone():
                raise ValueError("A canonical subscription already uses the destination key; review its billing decisions first.")
            _add(operations, "subscriptions", old, {**old, "account_id": target["id"], "scope": scope, "normalized_key": new_key})
            moved.append(old["id"])
    learning_moved = 0
    if "subscription_learning" in tables:
        planned = {}
        for raw in conn.execute("SELECT * FROM subscription_learning"):
            old = dict(raw)
            parts = old["normalized_key"].rsplit("|", 2)
            if len(parts) != 3 or parts[-1] != source["id"]:
                continue
            merchant, scope, _ = parts
            if target["scope"] == "business":
                scope = "business"
            new_key = merchant + "|" + scope + "|" + target["id"]
            existing = history._row(conn, "subscription_learning", new_key, "normalized_key") or planned.get(new_key)
            if existing and existing["decision"] != old["decision"]:
                raise ValueError("Subscription learning decisions conflict at the destination key.")
            # An identical existing decision stays unchanged. Both old and new
            # rows are journaled when renaming a key so undo restores the exact
            # decision timestamps and removes only our inserted destination.
            _add(operations, "subscription_learning", old, None, "normalized_key")
            if existing is None:
                after = {**old, "normalized_key": new_key}
                _add(operations, "subscription_learning", None, after, "normalized_key")
                planned[new_key] = after
            learning_moved += 1
    return moved, learning_moved


def plan_repair(conn, manual_account_id, canonical_account_id, reviewed_pairs=None):
    """Read-only plan. Reviewed pairs are {duplicate,canonical,evidence} dicts."""
    if manual_account_id == canonical_account_id:
        raise ValueError("Select two distinct accounts.")
    source = history._row(conn, "accounts", manual_account_id)
    target = history._row(conn, "accounts", canonical_account_id)
    if not source or not target:
        raise ValueError("Selected account not found.")
    if source.get("plaid_account_id") or source.get("item_id"):
        raise ValueError("The source must be a manually imported account, without a bank connection.")
    if not target.get("plaid_account_id") or target.get("archived"):
        raise ValueError("The canonical account must have an active bank connection.")
    if (source.get("type") != "depository" or target.get("type") != "depository"
            or target.get("subtype") != "checking" or source.get("subtype") not in (None, "", "checking")
            or not source.get("mask") or source["mask"] != target.get("mask")
            or source.get("iso_currency") != target.get("iso_currency") or source.get("scope") != target.get("scope")):
        raise ValueError("Account type, checking subtype, mask, currency and scope must agree.")
    aliases = history.aliases(conn)
    if canonical_account_id in aliases or aliases.get(manual_account_id, canonical_account_id) != canonical_account_id:
        raise ValueError("The selected accounts have a conflicting alias.")
    manual = [dict(r) for r in conn.execute("SELECT * FROM transactions WHERE account_id=? ORDER BY posted,id", (manual_account_id,))]
    bank = [dict(r) for r in conn.execute("SELECT * FROM transactions WHERE account_id=? ORDER BY posted,id", (canonical_account_id,))]
    if any(t.get("plaid_transaction_id") for t in manual):
        raise ValueError("The manual source contains bank transactions; review before repair.")
    if not manual and aliases.get(manual_account_id) == canonical_account_id:
        return {"already_repaired": True, "operations": [], "pairs": [], "summary": {"quarantined": 0, "history_moved": 0}}
    bank = [t for t in bank if t.get("plaid_transaction_id")]
    manual_groups, bank_groups = defaultdict(list), defaultdict(list)
    for tx in manual:
        if not tx.get("pending") and _cents(tx["amount"]) != 0:
            manual_groups[_key(tx)].append(tx)
    for tx in bank:
        if not tx.get("pending") and _cents(tx["amount"]) != 0:
            bank_groups[_key(tx)].append(tx)
    matched = []
    ambiguous = []
    for key, originals in manual_groups.items():
        candidates = bank_groups.get(key, [])
        if not candidates:
            continue
        # Identical repeated purchases are retained as a multiset. If annotations
        # differ, we cannot infer which provider ID owns which manual decision.
        if len(originals) != len(candidates) or (len(originals) > 1 and len({_annotation(t) for t in originals}) > 1):
            ambiguous.append({"manual_ids": [t["id"] for t in originals], "bank_ids": [t["id"] for t in candidates],
                              "reason": "Different multiplicity or distinct manual decisions on indistinguishable purchases."})
            continue
        for old, canonical in zip(originals, candidates):
            matched.append((old, canonical, "Exact signed amount and posting date; equivalent bank/Copilot descriptor."))
    by_id = {t["id"]: t for t in manual + bank}
    used_manual = {t["id"] for t, _, _ in matched}
    used_bank = {t["id"] for _, t, _ in matched}
    for pair in reviewed_pairs or []:
        old, canonical = by_id.get(pair.get("duplicate")), by_id.get(pair.get("canonical"))
        if (not old or not canonical or old["account_id"] != manual_account_id or canonical["account_id"] != canonical_account_id
                or old["id"] in used_manual or canonical["id"] in used_bank):
            raise ValueError("A reviewed pair is missing, in the wrong account, or already matched.")
        if not str(pair.get("evidence") or "").strip():
            raise ValueError("A reviewed pair needs its evidence recorded.")
        if _cents(old["amount"]) != _cents(canonical["amount"]) or _cents(old["amount"]) == 0:
            raise ValueError("A reviewed pair must retain the same signed amount.")
        if abs((date.fromisoformat(old["posted"]) - date.fromisoformat(canonical["posted"])).days) > 7:
            raise ValueError("A reviewed pair's dates differ by more than seven days.")
        if old.get("pending") or canonical.get("pending"):
            raise ValueError("Pending holds require explicit bank replacement evidence; this repair cannot infer it.")
        matched.append((old, canonical, str(pair["evidence"])))
        used_manual.add(old["id"]); used_bank.add(canonical["id"])
    dates = [date.fromisoformat(old["posted"]) for old, _, _ in matched]
    if len(matched) < 5 or not dates or (max(dates) - min(dates)).days < 7:
        raise ValueError("Broad matching posted history is required; a shared account mask is insufficient.")
    operations, pairs = [], []
    references = history._transaction_references(conn)
    manual_preserved = 0
    for old, canonical, evidence in matched:
        merged = history._merged_transaction(canonical, old)
        manual_preserved += merged != canonical
        _add(operations, "transactions", canonical, merged)
        for table, column in references:
            for row in conn.execute(f'SELECT * FROM "{table}" WHERE "{column}"=?', (old["id"],)):
                before = dict(row)
                _add(operations, table, before, {**before, column: canonical["id"]})
        _add(operations, "transactions", old, None)
        pairs.append({"duplicate": old["id"], "canonical": canonical["id"], "evidence": evidence})
    unmatched = [t for t in manual if t["id"] not in used_manual]
    for old in unmatched:
        after = {**old, "account_id": canonical_account_id}
        if old.get("scope_override") is None:
            after["scope"] = target["scope"]
        _add(operations, "transactions", old, after)
    _add(operations, "accounts", source, {**source, "archived": 1})
    if manual_account_id not in aliases:
        _add(operations, "transaction_account_aliases", None, {
            "duplicate_account_id": manual_account_id, "canonical_account_id": canonical_account_id,
            "reason": "Verified manual checking history reconciled with bank history; unique records retained.",
            "created_at": history.now()}, "duplicate_account_id")
    subscription_ids, learning_moved = _move_subscription_references(conn, source, target, operations)
    return {"already_repaired": False, "operations": operations, "pairs": pairs,
            "unmatched_ids": [t["id"] for t in unmatched], "ambiguous_groups": ambiguous,
            "unresolved_pending_ids": [t["id"] for t in unmatched if t.get("pending")],
            "subscription_ids_moved": subscription_ids,
            "summary": {"quarantined": len(pairs), "history_moved": len(unmatched),
                        "manual_records_preserved": manual_preserved,
                        "unmatched_pending_preserved": sum(bool(t.get("pending")) for t in unmatched),
                        "subscriptions_moved": len(subscription_ids), "subscription_learning_moved": learning_moved,
                        "bank_transaction_count": len(bank), "bank_balance_preserved": target["balance"]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--manual-account")
    parser.add_argument("--canonical-account")
    parser.add_argument("--reviewed-pairs", help="Private JSON file with explicitly reviewed exceptional pairs")
    parser.add_argument("--output", help="Write the complete private preview, including original rows, here")
    parser.add_argument("--backup-dir")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--undo", metavar="RUN_ID")
    args = parser.parse_args()
    if not args.undo and (not args.manual_account or not args.canonical_account):
        parser.error("--manual-account and --canonical-account are required")
    database = Path(args.database).resolve()
    mutating = args.apply or bool(args.undo)
    conn = sqlite3.connect(database.as_uri() + ("?mode=rw" if mutating else "?mode=ro"), uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        if mutating:
            folder = Path(args.backup_dir or database.parent / "transaction-repair-backups")
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            backup = folder / ("checking-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8] + ".sqlite3")
            with sqlite3.connect(backup) as saved:
                conn.backup(saved)
            os.chmod(backup, 0o600)
            conn.execute("BEGIN IMMEDIATE")
        else:
            conn.execute("BEGIN")
        if args.undo:
            history.undo_run(conn, args.undo)
            output = {"undone": args.undo, "backup": str(backup)}
        else:
            reviewed = json.loads(Path(args.reviewed_pairs).read_text(encoding="utf-8-sig")) if args.reviewed_pairs else None
            plan = plan_repair(conn, args.manual_account, args.canonical_account, reviewed)
            if args.output:
                destination = Path(args.output)
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                destination.write_text(json.dumps(plan, indent=2), encoding="utf-8")
                os.chmod(destination, 0o600)
            output = {"dry_run": not args.apply, "summary": plan["summary"], "ambiguous_groups": plan.get("ambiguous_groups", []),
                      "unresolved_pending_ids": plan.get("unresolved_pending_ids", [])}
            if args.apply:
                output.update(run_id=history.apply_plan(conn, plan), backup=str(backup))
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Foreign key check failed; repair rolled back.")
        conn.commit()
        print(json.dumps(output, indent=2))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
