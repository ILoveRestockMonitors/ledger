"""Monthly, scope-safe consolidation of unbudgeted categories into budgeted categories.

Rules:
1. Any category that ALREADY has a budget set on it in Ledger never moves into
   another category (e.g. Software & SaaS stays Software & SaaS; Office Supplies
   stays Office Supplies whenever it has a budget).
2. Every category WITHOUT a budget in the selected month consolidates into a
   category that DOES have a budget in the same scope (Personal -> Personal
   budgets, Business -> Business budgets).
3. Always previewed first with exact transaction counts, amounts, and row
   fingerprints; applying creates a reversible batch in ``category_edit_batches``.
"""
from datetime import date, datetime
import json
import secrets
import time
import unicodedata

import budget_overview
import category_rules
import db
import receipt_store


def _norm(name):
    return " ".join(unicodedata.normalize("NFKC", str(name or "")).split()).casefold()


TRANSFER_CATEGORY_NAMES = frozenset({
    "credit card payment",
    "internal transfers",
    "loan payment",
})
UNCATEGORIZED_NAMES = frozenset({"uncategorized", "uncategorised", ""})

# Ordered bidirectional affinities: when category X has no budget, pick the
# first candidate in AFFINITIES[X] that has an active budget in the same scope.
# Because pairs list each other (e.g. Entertainment <-> Shopping), moving a
# budget from Shopping to Entertainment automatically reverses the direction.
AFFINITIES = {
    "entertainment": ("shopping", "subscriptions", "eat out", "travel & vacation"),
    "shopping": ("entertainment", "subscriptions", "home & garden", "office supplies", "personal care", "education", "kids & pets"),
    "subscriptions": ("software & saas", "shopping", "entertainment", "internet & phone", "bills & utilities"),
    "software & saas": ("subscriptions", "hardware & equipment", "office supplies", "other business", "work expenses", "shopping"),
    "hardware & equipment": ("office supplies", "software & saas", "other business", "work expenses", "shopping"),
    "tiktok accounts": ("advertising", "software & saas", "subscriptions", "other business", "shopping"),
    "groceries": ("eat out", "dining & coffee", "business meals", "shopping"),
    "eat out": ("groceries", "dining & coffee", "business meals", "entertainment", "shopping"),
    "dining & coffee": ("eat out", "groceries", "business meals", "entertainment", "shopping"),
    "business meals": ("eat out", "dining & coffee", "groceries", "business travel", "other business", "office supplies", "software & saas"),
    "bank fees & interest": ("debt repayment (and fees)", "payment processing", "other business", "bills & utilities", "software & saas"),
    "debt repayment (and fees)": ("bank fees & interest", "payment processing", "bills & utilities", "other business"),
    "payment processing": ("bank fees & interest", "debt repayment (and fees)", "software & saas", "other business"),
    "cash & checks": ("debt repayment (and fees)", "bank fees & interest", "other business", "shopping"),
    "insurance": ("pet insurance", "car", "healthcare", "bills & utilities", "other business"),
    "pet insurance": ("insurance", "kids & pets", "healthcare", "shopping"),
    "kids & pets": ("pet insurance", "shopping", "healthcare", "groceries", "eat out"),
    "transport & fuel": ("gas station", "car", "parking", "business travel", "travel & vacation"),
    "gas station": ("transport & fuel", "car", "parking", "travel & vacation"),
    "car": ("gas station", "transport & fuel", "parking", "insurance"),
    "parking": ("car", "gas station", "transport & fuel", "travel & vacation"),
    "health & fitness": ("gym", "healthcare", "personal care", "shopping"),
    "gym": ("health & fitness", "healthcare", "personal care"),
    "healthcare": ("health & fitness", "personal care", "gym", "insurance"),
    "personal care": ("healthcare", "health & fitness", "gym", "shopping"),
    "travel": ("travel & vacation", "business travel", "gas station", "car", "eat out", "shopping"),
    "travel & vacation": ("travel", "business travel", "gas station", "car", "eat out", "shopping"),
    "business travel": ("travel & vacation", "travel", "business meals", "transport & fuel", "other business", "software & saas"),
    "office supplies": ("other business", "work expenses", "hardware & equipment", "shipping & postage", "shopping", "software & saas"),
    "home & garden": ("shopping", "office supplies", "rent / mortgage", "bills & utilities"),
    "education": ("software & saas", "subscriptions", "professional services", "office supplies", "shopping"),
    "shipping & postage": ("inventory", "office supplies", "other business", "software & saas", "shopping"),
    "inventory": ("shipping & postage", "office supplies", "other business", "software & saas", "shopping"),
    "advertising": ("software & saas", "professional services", "contractors", "other business", "shopping"),
    "contractors": ("professional services", "other business", "software & saas", "work expenses"),
    "professional services": ("contractors", "other business", "office supplies", "software & saas", "debt repayment (and fees)"),
    "other business": ("office supplies", "professional services", "software & saas", "shopping"),
    "work expenses": ("office supplies", "other business", "software & saas", "shopping"),
    "bills & utilities": ("utilities", "internet & phone", "rent / mortgage", "studio / coworking", "debt repayment (and fees)", "shopping"),
    "utilities": ("bills & utilities", "internet & phone", "rent / mortgage", "studio / coworking", "debt repayment (and fees)", "shopping"),
    "internet & phone": ("bills & utilities", "utilities", "subscriptions", "software & saas", "shopping"),
    "rent / mortgage": ("bills & utilities", "studio / coworking", "debt repayment (and fees)", "shopping"),
    "studio / coworking": ("rent / mortgage", "office supplies", "bills & utilities", "other business", "software & saas"),
}

FALLBACK_ORDER = {
    "personal": ("shopping", "eat out", "debt repayment (and fees)", "personal care"),
    "business": ("other business", "office supplies", "software & saas", "business meals", "shipping & postage"),
}


def _choose_target(source_name, tx_scope, scoped_targets):
    """Pick the best budgeted category in ``tx_scope`` for an unbudgeted category."""
    if not scoped_targets:
        return None
    by_norm = {_norm(t["name"]): t for t in scoped_targets}
    src_key = _norm(source_name)
    for candidate_name in AFFINITIES.get(src_key, ()):
        if candidate_name in by_norm:
            return by_norm[candidate_name]
    # Reverse check: if a budgeted category lists src_key in its own affinities
    for target in scoped_targets:
        t_key = _norm(target["name"])
        if src_key in AFFINITIES.get(t_key, ()):
            return target
    for fallback_name in FALLBACK_ORDER.get(tx_scope, ()):
        if fallback_name in by_norm:
            return by_norm[fallback_name]
    # Deterministic fallback: highest monthly budget in this scope
    return sorted(scoped_targets, key=lambda t: (-float(t["month_limit"] or 0), t["name"]))[0]


def _normalize_scope(scope):
    if scope in (None, "", "everything", "all"):
        return None
    if scope in ("personal", "business"):
        return scope
    raise ValueError("Choose All, Personal, or Business.")


def _budget_maps(conn):
    budget_rows = [dict(r) for r in conn.execute("""
        SELECT b.id, b.category_id, b.scope, b.month_limit, c.name, c.icon, c.kind
        FROM budgets b
        JOIN categories c ON c.id = b.category_id
        WHERE c.kind = 'expense' AND b.month_limit > 0
        ORDER BY c.name, b.id
    """).fetchall()]
    # Rule 1: ANY category that has a budget set on it anywhere stays as itself!
    any_budgeted_ids = {b["category_id"] for b in budget_rows}
    by_scope = {"personal": {}, "business": {}}
    for b in budget_rows:
        target_scopes = ("personal", "business") if b["scope"] == "all" else (b["scope"],)
        for s in target_scopes:
            if s not in by_scope:
                continue
            entry = by_scope[s].setdefault(b["category_id"], {
                "id": b["category_id"],
                "name": b["name"],
                "icon": b["icon"] or "",
                "month_limit": 0.0,
            })
            entry["month_limit"] = round(entry["month_limit"] + float(b["month_limit"] or 0), 2)
    scoped_targets = {
        s: sorted(by_scope[s].values(), key=lambda x: x["name"].casefold())
        for s in ("personal", "business")
    }
    return any_budgeted_ids, scoped_targets


def preview(month=None, scope=None, as_of=None):
    """Build an exact, fingerprinted consolidation preview for ``month``."""
    receipt_store.init_schema()
    category_rules.init_schema()
    clean_scope = _normalize_scope(scope)
    today = as_of or date.today()
    start, end = budget_overview.month_bounds(month, today)
    month_key = start[:7]
    month_label = datetime.strptime(month_key + "-01", "%Y-%m-%d").strftime("%B %Y")

    conn = db._conn()
    try:
        any_budgeted_ids, scoped_targets = _budget_maps(conn)
        sql = """
            SELECT t.*, COALESCE(a.name, 'Cash / manual') account_name, a.mask account_mask,
                   COALESCE(a.archived, 0) archived, cat.name category_name, cat.kind category_kind,
                   EXISTS(SELECT 1 FROM receipt_allocations ra WHERE ra.transaction_id = t.id AND ra.active = 1) has_split
            FROM transactions t
            LEFT JOIN accounts a ON a.id = t.account_id
            LEFT JOIN categories cat ON cat.id = t.category_id
            WHERE t.amount < 0
              AND COALESCE(t.is_transfer, 0) = 0
              AND COALESCE(a.archived, 0) = 0
              AND t.posted >= ? AND t.posted < ?
        """ + (" AND t.scope = ?" if clean_scope else "") + " ORDER BY t.posted DESC, t.id"
        args = (start, end, *((clean_scope,) if clean_scope else ()))
        raw_rows = [dict(r) for r in conn.execute(sql, args).fetchall()]
        decorated = receipt_store.decorate_transactions([dict(r) for r in raw_rows])
        display_by_id = {r["id"]: r.get("display_name") or r.get("merchant") or r.get("name") for r in decorated}

        kept_budgeted = set()
        skipped_splits = 0
        skipped_uncategorized = 0
        missing_budget_scopes = set()
        grouped = {}

        for row in raw_rows:
            cid = row.get("category_id")
            cname = (row.get("category_name") or "").strip()
            cnorm = _norm(cname)
            if cnorm in TRANSFER_CATEGORY_NAMES:
                continue
            if not cid or cnorm in UNCATEGORIZED_NAMES or row.get("category_kind") != "expense":
                skipped_uncategorized += 1
                continue
            # Hard Rule 1: If this category ALREADY has a budget set on it, NEVER move it!
            if cid in any_budgeted_ids:
                kept_budgeted.add(cname)
                continue
            if row.get("has_split"):
                skipped_splits += 1
                continue
            tx_scope = row["scope"]
            targets = scoped_targets.get(tx_scope) or []
            if not targets:
                missing_budget_scopes.add(tx_scope)
                continue
            chosen = _choose_target(cname, tx_scope, targets)
            if not chosen or chosen["id"] == cid:
                continue
            gkey = f"{tx_scope}:{cid}"
            bucket = grouped.setdefault(gkey, {
                "group_key": gkey,
                "scope": tx_scope,
                "source_category_id": cid,
                "source_category_name": cname,
                "target_category_id": chosen["id"],
                "target_category_name": chosen["name"],
                "target_budget_limit": chosen["month_limit"],
                "available_targets": targets,
                "rows": [],
            })
            bucket["rows"].append(row)

        groups_out = []
        preview_groups_payload = {}
        for gkey, bucket in sorted(
            grouped.items(),
            key=lambda kv: (0 if kv[1]["scope"] == "personal" else 1, -sum(abs(r["amount"]) for r in kv[1]["rows"]), kv[1]["source_category_name"].casefold()),
        ):
            rows = bucket["rows"]
            total_amt = round(sum(abs(float(r["amount"])) for r in rows), 2)
            preview_groups_payload[gkey] = {
                "scope": bucket["scope"],
                "source_category_id": bucket["source_category_id"],
                "source_category_name": bucket["source_category_name"],
                "default_target_id": bucket["target_category_id"],
                "rows": [{"id": r["id"], "fingerprint": category_rules._fingerprint(r)} for r in rows],
            }
            groups_out.append({
                "group_key": gkey,
                "scope": bucket["scope"],
                "source_category_id": bucket["source_category_id"],
                "source_category_name": bucket["source_category_name"],
                "target_category_id": bucket["target_category_id"],
                "target_category_name": bucket["target_category_name"],
                "target_budget_limit": bucket["target_budget_limit"],
                "available_targets": bucket["available_targets"],
                "count": len(rows),
                "total": total_amt,
                "transactions": [{
                    "id": r["id"],
                    "posted": r["posted"],
                    "display_name": display_by_id.get(r["id"]) or r.get("merchant") or r.get("name"),
                    "name": r["name"],
                    "merchant": r["merchant"],
                    "amount": r["amount"],
                    "pending": bool(r["pending"]),
                    "account_name": r["account_name"],
                    "account_mask": r["account_mask"],
                } for r in rows],
            })

        token = secrets.token_hex(24)
        payload = {
            "budget_consolidation": True,
            "month": month_key,
            "scope": clean_scope or "everything",
            "groups": preview_groups_payload,
        }
        conn.execute("DELETE FROM category_edit_previews WHERE expires_at < ?", (time.time(),))
        conn.execute("INSERT INTO category_edit_previews VALUES(?,?,?)", (token, json.dumps(payload), time.time() + 900))
        conn.commit()

        total_count = sum(g["count"] for g in groups_out)
        total_amount = round(sum(g["total"] for g in groups_out), 2)
        return {
            "preview_id": token,
            "month": month_key,
            "month_label": month_label,
            "scope": clean_scope or "everything",
            "total_count": total_count,
            "total_amount": total_amount,
            "group_count": len(groups_out),
            "groups": groups_out,
            "kept_budgeted_categories": sorted(kept_budgeted, key=str.casefold),
            "skipped_splits": skipped_splits,
            "skipped_uncategorized": skipped_uncategorized,
            "missing_budget_scopes": sorted(missing_budget_scopes),
        }
    finally:
        conn.close()


def apply(preview_id, selections=None):
    """Apply a confirmed consolidation preview and return a reversible ``batch_id``."""
    if not isinstance(preview_id, str) or not preview_id.strip():
        raise ValueError("Open Consolidate categories again to review a fresh preview.")
    category_rules.init_schema()
    receipt_store.init_schema()
    conn = db._conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        saved = conn.execute("SELECT * FROM category_edit_previews WHERE id=?", (preview_id.strip(),)).fetchone()
        if not saved or saved["expires_at"] < time.time():
            raise ValueError("This consolidation preview expired. Click Consolidate categories again to review.")
        payload = json.loads(saved["payload"])
        if not payload.get("budget_consolidation"):
            raise ValueError("Invalid consolidation preview.")
        saved_groups = payload.get("groups") or {}
        if not saved_groups:
            conn.execute("DELETE FROM category_edit_previews WHERE id=?", (preview_id.strip(),))
            conn.commit()
            return {"ok": True, "changed": 0, "batch_id": None}

        if selections is None:
            chosen_map = {gkey: g["default_target_id"] for gkey, g in saved_groups.items()}
        elif isinstance(selections, dict):
            chosen_map = {str(k): str(v) for k, v in selections.items() if v}
        else:
            raise ValueError("Invalid consolidation selection.")

        if not chosen_map:
            raise ValueError("Keep at least one category checked to consolidate, or click Cancel.")
        unknown = set(chosen_map) - set(saved_groups)
        if unknown:
            raise ValueError("Selection does not match this preview. Reopen Consolidate categories.")

        _, scoped_targets = _budget_maps(conn)
        allowed_by_scope = {s: {t["id"]: t["name"] for t in targets} for s, targets in scoped_targets.items()}

        all_ids = [item["id"] for gkey in chosen_map for item in saved_groups[gkey]["rows"]]
        current_rows = {r["id"]: r for r in category_rules._rows(conn, all_ids)} if all_ids else {}

        before = []
        updates = []
        for gkey, target_id in chosen_map.items():
            group = saved_groups[gkey]
            g_scope = group["scope"]
            if target_id not in allowed_by_scope.get(g_scope, {}):
                raise ValueError(f"Choose a category with an active {g_scope} budget.")
            for item in group["rows"]:
                row = current_rows.get(item["id"])
                if not row or category_rules._fingerprint(row) != item["fingerprint"]:
                    raise ValueError("A transaction in this month changed since the preview opened. Click Consolidate categories again to review.")
                before.append({
                    "id": row["id"],
                    "category_id": row["category_id"],
                    "category_override": row["category_override"],
                    "target_category_id": target_id,
                })
                updates.append((target_id, row["id"]))

        now = datetime.now().isoformat(timespec="microseconds")
        for target_id, tx_id in updates:
            conn.execute("UPDATE transactions SET category_id=?, category_override=1 WHERE id=?", (target_id, tx_id))

        batch_id = secrets.token_hex(16)
        audit = {
            "multi_target": True,
            "category_id": None,
            "before": before,
            "rule_before": None,
            "rule_changed": False,
            "name_key": "",
            "scope": payload.get("scope", ""),
            "rule_updated_at": now,
        }
        conn.execute("INSERT INTO category_edit_batches(id,payload,created_at) VALUES(?,?,?)", (batch_id, json.dumps(audit), now))
        conn.execute("DELETE FROM category_edit_previews WHERE id=?", (preview_id.strip(),))
        conn.commit()
        return {"ok": True, "changed": len(updates), "batch_id": batch_id}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
