"""Conservative, explainable category suggestions without a remote AI service.

Only unassigned expenses are eligible. Explicit merchant rules come first, then
unanimous user choices within the same scope, known specialist merchants, and
the bank's structured taxonomy. Ambiguous retailers remain unassigned unless
the user has explicitly saved a rule. ``choose`` never writes; ``backfill`` is
a preview by default, with compare-and-set writes and a reversible audit when
explicitly applied.
"""
import re
import unicodedata
import uuid
from datetime import datetime, timezone

import db


UNCATEGORIZED = {"uncategorized", "uncategorised"}


def _key(value):
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())


def _name_key(tx):
    return _key(tx.get("name") if tx.get("name_override") else tx.get("merchant") or tx.get("name"))


def _scope(tx):
    # Account classification is the default; a deliberate purchase override wins.
    return tx.get("scope_override") or tx.get("account_scope") or tx.get("scope") or "personal"


def _tables(conn):
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _category_rows(categories, conn):
    if categories is None:
        return [dict(r) for r in conn.execute("SELECT * FROM categories")]
    if isinstance(categories, dict):
        return [dict(value, id=value.get("id", key)) for key, value in categories.items()]
    return [dict(row) for row in categories]


def _unassigned(tx, categories):
    cid = tx.get("category_id")
    if not cid:
        return True
    return any(c["id"] == cid and _key(c.get("name")) in UNCATEGORIZED for c in categories)


# Payment processors and department stores do not tell us what was bought.
# Even a single user's earlier category is insufficient to classify them all.
_AMBIGUOUS = re.compile(
    r"\b(?:amazon|amzn|apple|paypal|venmo|zelle|walmart|wal mart|target|costco|"
    r"sam'?s club|ebay|etsy|klarna|afterpay|affirm|splitit)\b", re.I)
_TRANSFER_NAME = re.compile(
    r"\b(?:funds transfer|transfer (?:from|to)|mobile payment|autopay payment|"
    r"epayment|card pymt|credit card payment|cashout|cash out|sent money)\b", re.I)


def _protected(tx, categories, receipts):
    pfc = tx.get("personal_finance_category") or {}
    primary = pfc.get("primary", "") if isinstance(pfc, dict) else pfc
    provider_protected = str(primary).upper().startswith(("TRANSFER_IN", "TRANSFER_OUT", "LOAN_PAYMENTS", "INCOME"))
    return (bool(tx.get("category_override")) or not _unassigned(tx, categories)
            or float(tx.get("amount") or 0) >= 0 or bool(tx.get("is_transfer"))
            or provider_protected
            or bool(tx.get("split_scope")) or tx.get("split_amount") is not None
            or tx.get("id") in receipts or bool(tx.get("receipt_allocations"))
            or bool(tx.get("has_receipt_allocations"))
            or bool(_TRANSFER_NAME.search(str(tx.get("name") or ""))))


def _category(categories, names):
    """Resolve existing category names, preferring the user's Copilot taxonomy."""
    by_name = {_key(c["name"]): c["id"] for c in categories if c.get("kind") == "expense"}
    return next((by_name[_key(name)] for name in names if _key(name) in by_name), None)


def _result(cid, reason, source, confidence):
    return {"category_id": cid, "reason": reason, "source": source, "confidence": confidence} if cid else None


def _context(conn, categories=None):
    tables = _tables(conn)
    receipt_ids = {r[0] for r in conn.execute("SELECT DISTINCT transaction_id FROM receipt_allocations WHERE active=1")} if "receipt_allocations" in tables else set()
    categories = _category_rows(categories, conn)
    # Only explicit user/import overrides are evidence; automatic guesses never
    # train subsequent guesses. Exclude itemized parents and transfers.
    history = [dict(r) for r in conn.execute("""SELECT t.*, a.scope account_scope
        FROM transactions t LEFT JOIN accounts a ON a.id=t.account_id
        WHERE t.category_override=1 AND t.category_id IS NOT NULL
          AND COALESCE(a.archived,0)=0
          AND t.amount<0 AND COALESCE(t.is_transfer,0)=0""")]
    history = [t for t in history if t["id"] not in receipt_ids and not t.get("split_scope") and t.get("split_amount") is None]
    return categories, history, receipt_ids, tables


def _learned(tx, categories, history):
    key = _name_key(tx)
    merchant = _key(tx.get("merchant"))
    allowed = {c["id"] for c in categories if c.get("kind") == "expense" and _key(c["name"]) not in UNCATEGORIZED}
    scoped = [t for t in history if _scope(t) == _scope(tx) and t.get("id") != tx.get("id")]
    matching = [t for t in scoped if _name_key(t) == key]
    label = "purchase name"
    if not matching and merchant and not tx.get("name_override"):
        # A renamed item often describes the purchase, not the whole merchant.
        matching = [t for t in scoped if not t.get("name_override") and _key(t.get("merchant")) == merchant]
        label = "merchant"
    choices = {t.get("category_id") for t in matching}
    if len(choices) != 1 or not choices.issubset(allowed):
        return None, bool(matching)
    return _result(next(iter(choices)), "Matches your previous category for this " + label + " in " + _scope(tx) + ".", "learned", 0.98), True


# Specialist merchants only. Token boundaries prevent, for example, Shell
# being matched inside a different shop name. No generic Apple/Amazon/PayPal.
_MERCHANTS = (
    (r"\b(?:pirate ship|usps|united states postal service|fedex|ups store)\b", "shipping"),
    (r"\b(?:anthropic|claude(?:\.ai)?|openrouter|openai|chatgpt|higgsfield|klingai|elevenlabs|reel\.farm|cursor ai|cursor, ai|adobe|canva|dropbox|notion)\b", "software"),
    (r"\b(?:netflix|spotify|hulu|disney\s*\+|disney plus|youtube premium|youtube music)\b", "subscription"),
    (r"\b(?:safeway|trader joe'?s|whole foods|kroger|sprouts farmers market|aldi)\b", "groceries"),
    (r"\b(?:starbucks|dunkin|chipotle|mcdonald'?s|burger king|taco bell|doordash|uber eats|grubhub)\b", "dining"),
    (r"\b(?:chevron|shell|arco|exxon|mobil|texaco|valero|sunoco)\b", "fuel"),
    (r"\b(?:planet fitness|24 hour fitness|anytime fitness|la fitness|crunch fitness)\b", "gym"),
    (r"\b(?:comcast|xfinity|verizon|t mobile|t-mobile|at&t)\b", "internet"),
    (r"\b(?:southwest airlines|united airlines|delta air lines|american airlines|alaska airlines|airbnb)\b", "travel"),
)


def _names(group, scope):
    business = scope == "business"
    return {
        "shipping": ["Shipping & Postage"],
        "software": ["Software & SaaS", "Work Expenses"] if business else ["Subscriptions"],
        "subscription": ["Subscriptions"],
        "groceries": ["Groceries"],
        "dining": ["Eat out", "Dining & Coffee"],
        "fuel": ["Gas station", "Transport & Fuel"],
        "gym": ["Gym", "Health & Fitness"],
        "internet": ["Internet & Phone"],
        "travel": ["Travel & Vacation", "Travel", "Business Travel"] if not business else ["Business Travel", "Travel & Vacation", "Travel"],
        "health": ["Healthcare", "Health & Fitness"],
        "personal_care": ["Personal Care"],
        "parking": ["Parking", "Transport & Fuel"],
        "transport": ["Transport & Fuel", "Car"],
        "car": ["Car", "Transport & Fuel"],
        "rent": ["Rent / Mortgage"],
        "utilities": ["Utilities"],
        "insurance": ["Insurance"],
        "fun": ["Entertainment"],
        "shopping": ["Shopping (other)", "Shopping"],
        "fees": ["debt repayment (and fees)", "Bank Fees & Interest"],
        "pets": ["Kids & Pets"],
    }.get(group, [])


_PFC_DETAIL = {
    "FOOD_AND_DRINK_GROCERIES": "groceries",
    "TRANSPORTATION_GAS": "fuel",
    "TRANSPORTATION_PARKING": "parking",
    "TRANSPORTATION_AUTOMOTIVE": "car",
    "PERSONAL_CARE_GYMS_AND_FITNESS_CENTERS": "gym",
    "RENT_AND_UTILITIES_RENT": "rent",
    "RENT_AND_UTILITIES_INTERNET_AND_CABLE": "internet",
    "RENT_AND_UTILITIES_TELEPHONE": "internet",
    "RENT_AND_UTILITIES_ELECTRICITY": "utilities",
    "RENT_AND_UTILITIES_GAS_AND_ELECTRICITY": "utilities",
    "RENT_AND_UTILITIES_WATER": "utilities",
    "RENT_AND_UTILITIES_SEWAGE_AND_WASTE_MANAGEMENT": "utilities",
    "GENERAL_SERVICES_INSURANCE": "insurance",
    "GENERAL_MERCHANDISE_PET_SUPPLIES": "pets",
}
_PFC_PRIMARY = {
    "FOOD_AND_DRINK": "dining", "MEDICAL": "health", "ENTERTAINMENT": "fun",
    "PERSONAL_CARE": "personal_care", "TRAVEL": "travel", "TRANSPORTATION": "transport",
    "BANK_FEES": "fees",
}


def _provider(tx, categories):
    pfc = tx.get("personal_finance_category") or {}
    if isinstance(pfc, str):
        pfc = {"detailed": pfc}
    primary = str(pfc.get("primary") or tx.get("category_primary") or "").upper()
    detailed = str(pfc.get("detailed") or tx.get("category_detailed") or "").upper()
    confidence = str(pfc.get("confidence_level") or "").upper()
    if confidence and confidence not in ("HIGH", "VERY_HIGH"):
        return None
    group = _PFC_DETAIL.get(detailed) or _PFC_PRIMARY.get(primary)
    # This is an explicit provider taxonomy, never a substring in a store name.
    if not group:
        group = next((v for k, v in _PFC_PRIMARY.items() if detailed.startswith(k + "_")), None)
    if not group:
        return None
    cid = _category(categories, _names(group, _scope(tx)))
    return _result(cid, "Bank category: " + (detailed or primary).replace("_", " ").lower() + ".", "bank", 0.94 if confidence == "VERY_HIGH" else 0.90)


def _choose(tx, conn, context):
    tx = dict(tx)
    categories, history, receipts, tables = context
    if tx.get("account_id") and "account_scope" not in tx:
        account = conn.execute("SELECT scope FROM accounts WHERE id=?", (tx["account_id"],)).fetchone()
        if account:
            tx["account_scope"] = account[0]
    if _protected(tx, categories, receipts):
        return None
    if "transaction_category_rules" in tables:
        import category_rules
        rule = category_rules.match(tx, conn=conn)
        if rule and rule.get("category_id") in {c["id"] for c in categories if c.get("kind") == "expense"}:
            return rule
    key = _name_key(tx)
    if not key:
        return None
    ambiguous = bool(_AMBIGUOUS.search(key) or _AMBIGUOUS.search(str(tx.get("merchant") or "")))
    if not ambiguous:
        learned, has_history = _learned(tx, categories, history)
        if learned:
            return learned
        # Conflicting manual choices carry more weight than any default guess.
        if has_history:
            return None
        for pattern, group in _MERCHANTS:
            if re.search(pattern, key, re.I):
                cid = _category(categories, _names(group, _scope(tx)))
                if cid:
                    return _result(cid, "Recognized specialist merchant: " + key + ".", "merchant", 0.92)
    # A useful detailed bank code can identify a mixed merchant's purchase;
    # general merchandise alone deliberately cannot.
    return _provider(tx, categories)


def choose(tx, categories=None, conn=None):
    """Return a suggestion or None; safe inside a caller's SQLite transaction."""
    own = conn is None
    conn = conn or db._conn()
    try:
        return _choose(tx, conn, _context(conn, categories))
    finally:
        if own:
            conn.close()


def init_schema(conn=None):
    own = conn is None
    conn = conn or db._conn()
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS category_picker_audit (
            run_id TEXT NOT NULL, transaction_id TEXT NOT NULL,
            previous_category_id TEXT, previous_category_override INTEGER,
            category_id TEXT NOT NULL, reason TEXT NOT NULL, source TEXT NOT NULL,
            confidence REAL NOT NULL, created_at TEXT NOT NULL,
            rolled_back_at TEXT, PRIMARY KEY(run_id, transaction_id))""")
        if own:
            conn.commit()
    finally:
        if own:
            conn.close()


def backfill(dry_run=True):
    """Preview/apply suggestions; preserves manual choices and receipt splits."""
    conn = db._conn()
    try:
        conn.execute("BEGIN" if dry_run else "BEGIN IMMEDIATE")
        context = _context(conn)
        categories = {c["id"]: c["name"] for c in context[0]}
        rows = [dict(r) for r in conn.execute("""SELECT t.*, a.scope account_scope FROM transactions t
            LEFT JOIN accounts a ON a.id=t.account_id LEFT JOIN categories c ON c.id=t.category_id
            WHERE (t.category_id IS NULL OR lower(c.name) IN ('uncategorized','uncategorised'))
              AND COALESCE(t.category_override,0)=0 AND t.amount<0 AND COALESCE(t.is_transfer,0)=0
              AND COALESCE(a.archived,0)=0
            ORDER BY t.posted,t.id""")]
        candidates = []
        for tx in rows:
            suggestion = _choose(tx, conn, context)
            if suggestion:
                candidates.append(dict(suggestion, transaction_id=tx["id"], name=tx.get("name"),
                    posted=tx.get("posted"), scope=_scope(tx), amount=tx["amount"],
                    previous_category_id=tx.get("category_id"),
                    category_name=categories.get(suggestion["category_id"])))
        run_id, changed = None, 0
        if not dry_run and candidates:
            init_schema(conn)
            run_id = "category_" + uuid.uuid4().hex
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            rows_by_id = {t["id"]: t for t in rows}
            for candidate in candidates:
                old = rows_by_id[candidate["transaction_id"]]
                updated = conn.execute("""UPDATE transactions SET category_id=? WHERE id=?
                    AND category_id IS ? AND COALESCE(category_override,0)=0""",
                    (candidate["category_id"], old["id"], old.get("category_id"))).rowcount
                if not updated:
                    continue
                conn.execute("""INSERT INTO category_picker_audit
                    (run_id,transaction_id,previous_category_id,previous_category_override,category_id,reason,source,confidence,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?)""", (run_id, old["id"], old.get("category_id"), old.get("category_override"),
                    candidate["category_id"], candidate["reason"], candidate["source"], candidate["confidence"], now))
                changed += updated
        conn.commit()
        return {"dry_run": bool(dry_run), "run_id": run_id, "considered_count": len(rows),
                "suggestion_count": len(candidates), "changed_count": changed, "candidates": candidates}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def rollback(run_id):
    """Undo this run's unchanged automatic categories; subsequent edits win."""
    conn = db._conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if "category_picker_audit" not in _tables(conn):
            conn.rollback()
            return {"run_id": run_id, "restored_count": 0, "skipped_count": 0}
        audit = [dict(r) for r in conn.execute("SELECT * FROM category_picker_audit WHERE run_id=? AND rolled_back_at IS NULL", (run_id,))]
        receipts = {r[0] for r in conn.execute("SELECT DISTINCT transaction_id FROM receipt_allocations WHERE active=1")} if "receipt_allocations" in _tables(conn) else set()
        restored = 0
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for row in audit:
            if row["transaction_id"] in receipts:
                continue
            updated = conn.execute("""UPDATE transactions SET category_id=? WHERE id=?
                AND category_id=? AND category_override IS ? AND COALESCE(category_override,0)=0""",
                (row["previous_category_id"], row["transaction_id"], row["category_id"], row["previous_category_override"])).rowcount
            if updated:
                restored += updated
                conn.execute("UPDATE category_picker_audit SET rolled_back_at=? WHERE run_id=? AND transaction_id=?", (now, run_id, row["transaction_id"]))
        conn.commit()
        return {"run_id": run_id, "restored_count": restored, "skipped_count": len(audit) - restored}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
