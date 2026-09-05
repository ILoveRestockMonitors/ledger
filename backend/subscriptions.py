"""Persistent recurring-payment and subscription domain.

The module deliberately depends only on the small database interface exposed by
``db.py``.  Detection is conservative about identity (merchant + account +
scope), but sensitive about timing: two regular charges can become a review
candidate while three or more charges can become an active recommendation.
"""
from __future__ import annotations

import calendar
import math
import re
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from urllib.parse import urlsplit

import db


CADENCES = {
    "weekly": 7,
    "biweekly": 14,
    "monthly": 30.4375,
    "quarterly": 91.3125,
    "semiannual": 182.625,
    "annual": 365.25,
}
STATUSES = {"candidate", "active", "cancel_requested", "canceled", "dismissed"}
DECISIONS = {"confirm", "activate", "dismiss", "canceled", "cancel", "accept_price", "keep_price"}

# A single posted charge is useful evidence for services whose billing is
# commonly monthly or annual.  Keep this list deliberately narrow and compare
# normalized names exactly, so an arbitrary one-off purchase is not promoted.
KNOWN_RECURRING_MERCHANTS = {
    "adobe creative cloud", "amazon prime", "apple music", "chatgpt",
    "claude", "copilot money", "disney plus", "google one", "hulu",
    "copilot money premium", "gumroad memberships", "in shape", "netflix",
    "netflix com", "rocket money", "rocket money premium", "skool",
    "skool memberships", "spotify", "youtube premium",
}


def init_schema():
    """Create subscription tables and indexes; safe to call on every boot."""
    c = db._conn()
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS subscriptions (
          id TEXT PRIMARY KEY,
          merchant TEXT NOT NULL,
          scope TEXT NOT NULL CHECK(scope IN ('business','personal')),
          account_id TEXT,
          amount REAL NOT NULL CHECK(amount > 0),
          cadence TEXT NOT NULL,
          custom_interval_days INTEGER,
          billing_day INTEGER,
          next_due TEXT,
          status TEXT NOT NULL DEFAULT 'candidate',
          confidence REAL NOT NULL DEFAULT 0,
          reason TEXT NOT NULL DEFAULT '',
          management_url TEXT,
          billing_channel TEXT,
          notes TEXT NOT NULL DEFAULT '',
          observed_amount REAL,
          price_review INTEGER NOT NULL DEFAULT 0,
          ignored_price REAL,
          normalized_key TEXT NOT NULL,
          last_seen TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sub_scope_status ON subscriptions(scope,status);
        CREATE INDEX IF NOT EXISTS idx_sub_key ON subscriptions(normalized_key);
        CREATE TABLE IF NOT EXISTS subscription_reviews (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          subscription_id TEXT NOT NULL,
          decision TEXT NOT NULL,
          created_at TEXT NOT NULL,
          FOREIGN KEY(subscription_id) REFERENCES subscriptions(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS subscription_learning (
          normalized_key TEXT PRIMARY KEY,
          decision TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        """
    )
    # Migrations for databases created by an earlier worker version.
    cols = {r["name"] for r in c.execute("PRAGMA table_info(subscriptions)").fetchall()}
    for name, typ in (("custom_interval_days", "INTEGER"), ("billing_day", "INTEGER"), ("source", "TEXT NOT NULL DEFAULT 'detected'"),
                      ("observed_amount", "REAL"), ("price_review", "INTEGER NOT NULL DEFAULT 0"), ("ignored_price", "REAL")):
        if name not in cols:
            c.execute(f"ALTER TABLE subscriptions ADD COLUMN {name} {typ}")
    c.commit()
    c.close()


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _norm(value):
    value = re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()
    return re.sub(r"\s+", " ", value) or "unknown merchant"


def _parse_day(value):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value or "")):
        return None
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _cadence(days):
    if days <= 0:
        return "custom"
    choices = sorted(CADENCES.items(), key=lambda kv: abs(days - kv[1]))
    name, expected = choices[0]
    tolerance = max(3.0, expected * 0.22)
    return name if abs(days - expected) <= tolerance else "custom"


def _amount_close(expected, actual):
    try:
        expected, actual = abs(float(expected)), abs(float(actual))
    except (TypeError, ValueError):
        return False
    return math.isfinite(expected) and math.isfinite(actual) and abs(expected - actual) <= max(0.5, expected * 0.20)


def _add_due(day, cadence, amount=None, anchor_day=None, custom_interval_days=None):
    if not day:
        return None
    days = CADENCES.get(cadence)
    if cadence == "custom":
        try: days = int(custom_interval_days)
        except (TypeError, ValueError): days = None
        if not days:
            return None
    if cadence in ("monthly", "quarterly", "semiannual", "annual"):
        months = {"monthly": 1, "quarterly": 3, "semiannual": 6, "annual": 12}[cadence]
        month = day.month - 1 + months
        year, month = day.year + month // 12, month % 12 + 1
        return date(year, month, min(anchor_day or day.day, calendar.monthrange(year, month)[1]))
    return day + timedelta(days=round(days))


def _monthly(amount, cadence):
    periods = {"weekly": 52.1775, "biweekly": 26.08875, "monthly": 12,
               "quarterly": 4, "semiannual": 2, "annual": 1}
    if cadence == "custom":
        raise ValueError("custom cadence requires an interval")
    return amount * periods[cadence] / 12


def _validate(data, partial=False):
    if not isinstance(data, dict):
        raise ValueError("subscription must be an object")
    if not partial and not str(data.get("merchant", "")).strip():
        raise ValueError("merchant is required")
    if not partial and "amount" not in data:
        raise ValueError("amount is required")
    if "scope" in data and data["scope"] not in ("business", "personal"):
        raise ValueError("scope must be business or personal")
    if "amount" in data:
        try:
            amount = float(data["amount"])
        except (TypeError, ValueError):
            raise ValueError("amount must be finite and positive")
    for field in ("observed_amount", "ignored_price"):
        if field in data and data[field] is not None:
            try: observed = float(data[field])
            except (TypeError, ValueError): raise ValueError(f"{field} must be finite and positive")
            if not math.isfinite(observed) or observed <= 0: raise ValueError(f"{field} must be finite and positive")
    if "price_review" in data and int(bool(data["price_review"])) != data["price_review"]:
        raise ValueError("price_review must be a boolean")
        if not math.isfinite(amount) or amount <= 0 or amount > 10_000_000:
            raise ValueError("amount must be finite and positive")
    if "cadence" in data and data["cadence"] not in set(CADENCES) | {"custom"}:
        raise ValueError("unsupported cadence")
    if data.get("cadence") == "custom":
        try: interval = int(data.get("custom_interval_days", 0))
        except (TypeError, ValueError): interval = 0
        if interval < 1 or interval > 366: raise ValueError("custom cadence requires custom_interval_days from 1 to 366")
    if "next_due" in data and data.get("next_due") is not None and not _parse_day(data["next_due"]):
        raise ValueError("next_due must be YYYY-MM-DD")
    if "management_url" in data and data.get("management_url") is not None:
        parsed = urlsplit(str(data["management_url"]))
        if parsed.scheme.lower() != "https" or not parsed.netloc:
            raise ValueError("management_url must be an https URL")
    if "confidence" in data:
        try:
            confidence = float(data["confidence"])
        except (TypeError, ValueError):
            raise ValueError("confidence must be finite")
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
    if "status" in data and data["status"] not in STATUSES:
        raise ValueError("unsupported subscription status")


def _row(row):
    out = dict(row)
    if out["cadence"] == "custom" and out.get("custom_interval_days"):
        out["monthly_equivalent"] = round(float(out["amount"]) * 365.25 / 12 / float(out["custom_interval_days"]), 2)
    else:
        out["monthly_equivalent"] = round(_monthly(float(out["amount"]), out["cadence"]), 2)
    out["monthly_cost"] = out["monthly_equivalent"]
    out["confidence"] = round(float(out.get("confidence") or 0), 3)
    out["price_review"] = bool(out.get("price_review"))
    return out


def _has_column(table, column):
    """Allow this module to run against old fixtures during migration."""
    return any(r["name"] == column for r in db.q(f"PRAGMA table_info({table})"))


def save(data):
    """Create or update a manually entered subscription and return its record."""
    if not isinstance(data, dict):
        raise ValueError("subscription must be an object")
    init_schema()
    sid = data.get("id") or "sub_" + uuid.uuid4().hex[:16]
    old = db.q1("SELECT * FROM subscriptions WHERE id=?", (sid,))
    if data.get("id") and not old:
        raise ValueError("subscription not found")
    # Validate the effective record.  This is important for PATCH-like edits:
    # a custom cadence, account scope, or required field may live in old.
    merged = dict(old or {})
    merged.update(data)
    if not old:
        merged.setdefault("scope", "personal")
        merged.setdefault("cadence", "monthly")
    _validate(merged, partial=False)
    now = _now()
    merchant = str(merged.get("merchant", "")).strip()
    scope = merged.get("scope", "personal")
    account_id = merged.get("account_id") or None
    amount = float(merged["amount"])
    cadence = merged.get("cadence", "monthly")
    if account_id:
        account = db.q1("SELECT scope FROM accounts WHERE id=? AND archived=0", (account_id,))
        if not account: raise ValueError("account not found")
        if account["scope"] != scope: raise ValueError("subscription scope must match account scope")
    custom_days = int(merged.get("custom_interval_days") or 0)
    due = merged.get("next_due")
    due_day = _parse_day(due)
    # A changed due date carries a new billing anchor unless the caller is
    # deliberately retaining a different anchor (for example Jan 31 -> Feb
    # 28).  The explicit field is the only way to request that behavior.
    if "billing_day" in data:
        billing_day = int(merged.get("billing_day") or 0)
    elif old and "next_due" in data:
        billing_day = due_day.day if due_day else 0
    else:
        billing_day = int(merged.get("billing_day") or (due_day or date.today()).day)
    if billing_day < 1 or billing_day > 31:
        raise ValueError("billing_day must be from 1 to 31")
    # Direct saves are manual edits.  Scans pass source=detected explicitly so
    # a user's corrected cadence and due date remain authoritative on rescans.
    source = data.get("source") if "source" in data else "manual"
    if source not in ("manual", "detected"):
        raise ValueError("unsupported subscription source")
    observed_amount = merged.get("observed_amount")
    price_review = int(bool(merged.get("price_review")))
    ignored_price = merged.get("ignored_price")
    # A direct amount edit is an explicit correction by the owner; clear any
    # pending observed-price notice.  Scan payloads carry source=manual and
    # the persisted review fields so they do not clear the notice.
    if old and "amount" in data and "source" not in data:
        observed_amount, price_review, ignored_price = None, 0, None
    values = (sid, merchant, scope, account_id, amount, cadence, custom_days or None, billing_day, due,
              merged.get("status", "active"), float(merged.get("confidence", 1)),
              merged.get("reason", "manual"), merged.get("management_url"),
              merged.get("billing_channel"), merged.get("notes", ""), observed_amount, price_review, ignored_price,
              _norm(merchant) + "|" + scope + "|" + str(account_id or ""), merged.get("last_seen"),
              old["created_at"] if old else now, now, source)
    db.ex("""INSERT INTO subscriptions(id,merchant,scope,account_id,amount,cadence,custom_interval_days,billing_day,next_due,status,confidence,reason,
             management_url,billing_channel,notes,observed_amount,price_review,ignored_price,normalized_key,last_seen,created_at,updated_at,source)
             VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
             ON CONFLICT(id) DO UPDATE SET merchant=excluded.merchant,scope=excluded.scope,account_id=excluded.account_id,
             amount=excluded.amount,cadence=excluded.cadence,custom_interval_days=excluded.custom_interval_days,billing_day=excluded.billing_day,next_due=excluded.next_due,status=excluded.status,
             confidence=excluded.confidence,reason=excluded.reason,management_url=excluded.management_url,
             billing_channel=excluded.billing_channel,notes=excluded.notes,observed_amount=excluded.observed_amount,price_review=excluded.price_review,ignored_price=excluded.ignored_price,normalized_key=excluded.normalized_key,
             last_seen=excluded.last_seen,updated_at=excluded.updated_at,source=excluded.source""", values)
    return _row(db.q1("SELECT * FROM subscriptions WHERE id=?", (sid,)))


def _infer(ts):
    ts = sorted(ts, key=lambda x: x["day"])
    intervals = [(b["day"] - a["day"]).days for a, b in zip(ts, ts[1:])]
    typical = sum(intervals) / len(intervals) if intervals else 0
    cadence = _cadence(typical)
    custom_days = round(typical) if cadence == "custom" else None
    expected = CADENCES.get(cadence, typical or 30.4375)
    if cadence != "custom" and len(intervals) > 1 and max(intervals) - min(intervals) > max(3.0, expected * 0.20):
        cadence = "custom"
        custom_days = round(sorted(intervals)[len(intervals) // 2])
        expected = custom_days
    interval_fit = max(0.0, 1.0 - (sum(abs(v - expected) for v in intervals) / len(intervals)) / max(expected, 1)) if intervals else 0
    amounts = [x["amount"] for x in ts]
    avg = sum(amounts) / len(amounts)
    variation = (max(amounts) - min(amounts)) / avg if avg else 1
    confidence = min(0.99, max(0.25, 0.42 + min(len(ts), 6) * 0.07 + interval_fit * 0.3 - min(variation, 1) * 0.2))
    next_due = _add_due(ts[-1]["day"], cadence, anchor_day=ts[0]["day"].day, custom_interval_days=custom_days)
    reason = f"{len(ts)} charges; approximately {round(typical)} days apart"
    if variation > 0.12:
        reason += "; amount varies or recently changed"
    return cadence, custom_days, round(amounts[-1], 2), round(confidence, 3), reason, next_due, variation


def scan():
    """Scan expenses and upsert candidates without duplicating prior scans."""
    init_schema()
    transfer_clause = " AND COALESCE(is_transfer,0)=0" if _has_column("transactions", "is_transfer") else ""
    has_pending = _has_column("transactions", "pending")
    pending_clause = " AND COALESCE(pending,0)=0" if has_pending else ""
    pending_field = "t.pending" if has_pending else "0 AS pending"
    category_field = "c.name AS category_name" if _has_column("transactions", "category_id") and _has_column("categories", "name") else "'' AS category_name"
    join_categories = " LEFT JOIN categories c ON c.id=t.category_id" if category_field.startswith("c.") else ""
    rows = db.q("SELECT t.id,t.merchant,t.name,t.scope,t.account_id,t.amount,t.posted," + pending_field + "," + category_field + " FROM transactions t" + join_categories + " WHERE t.amount<0" + transfer_clause.replace("is_transfer", "t.is_transfer") + pending_clause.replace("pending", "t.pending") + " ORDER BY t.posted")
    groups = defaultdict(list)
    for r in rows:
        day = _parse_day(r.get("posted"))
        if not day or day > date.today():
            continue
        merchant = r.get("merchant") or r.get("name") or "Unknown merchant"
        key = _norm(merchant) + "|" + r["scope"] + "|" + str(r.get("account_id") or "")
        groups[key].append({"day": day, "amount": abs(float(r["amount"])), "tx_id": r["id"], "pending": bool(r.get("pending")), "merchant": merchant, "scope": r["scope"], "account_id": r.get("account_id"), "category_name": r.get("category_name", "")})
    existing = {r["normalized_key"]: r for r in db.q("SELECT * FROM subscriptions")}
    found = []
    for key, ts in groups.items():
        old = existing.get(key)
        if old is None:
            # A manual subscription without an account is intentionally a
            # scope-wide record.  Reuse it when a bank transaction later
            # supplies an account, rather than creating a duplicate monthly
            # commitment for the same exact merchant.
            manual_matches = [candidate for candidate in existing.values()
                              if candidate.get("source") == "manual"
                              and not candidate.get("account_id")
                              and candidate.get("scope") == ts[0]["scope"]
                              and _norm(candidate.get("merchant")) == _norm(ts[-1]["merchant"])]
            if len(manual_matches) > 1:
                # Do not guess which of two scope-wide manual records the
                # account-backed observations belong to, and do not create a
                # third detected commitment in their place.
                continue
            old = manual_matches[0] if len(manual_matches) == 1 else None
        known_single = _norm(ts[-1]["merchant"]) in KNOWN_RECURRING_MERCHANTS or old is not None
        if len(ts) < 2 and not known_single:
            continue
        if any((b["day"] - a["day"]).days <= 0 for a, b in zip(ts, ts[1:])):
            continue
        cadence, custom_days, amount, confidence, reason, next_due, variation = _infer(ts)
        if len(ts) == 1:
            cadence, custom_days = "monthly", None
            next_due = _add_due(ts[-1]["day"], cadence, anchor_day=ts[-1]["day"].day)
            confidence = 0.25
            reason = "1 posted charge from a commonly recurring merchant; confirm whether it repeats"
        elif cadence == "custom" and (not custom_days or not 1 <= custom_days <= 366):
            # An unsupported interval is not evidence of a subscription we
            # can safely schedule; leave it out of this scan rather than
            # allowing a malformed custom record to abort all detection.
            continue
        # A single skipped month should still be reviewable; huge gaps are custom.
        learning = db.q1("SELECT decision FROM subscription_learning WHERE normalized_key=?", (key,))
        if learning and learning["decision"] == "dismiss":
            continue
        recent_enough = (date.today() - ts[-1]["day"]).days <= max(60, round(CADENCES.get(cadence, custom_days or 30) * 2.5))
        cycle_keys = set()
        for item in ts:
            if cadence == "monthly": cycle_keys.add((item["day"].year, item["day"].month))
            elif cadence == "quarterly": cycle_keys.add((item["day"].year, (item["day"].month - 1) // 3))
            elif cadence == "semiannual": cycle_keys.add((item["day"].year, (item["day"].month - 1) // 6))
            elif cadence == "annual": cycle_keys.add(item["day"].year)
            else: cycle_keys.add(item["day"])
        forbidden_text = " ".join([_norm(ts[-1]["merchant"])] + [_norm(x.get("category_name")) for x in ts])
        forbidden_merchant = any(word in forbidden_text.split() for word in {"grocery", "groceries", "supermarket", "fuel", "gas", "dining", "restaurant", "coffee"}) or any(name in forbidden_text for name in ("kroger", "safeway", "whole foods", "costco", "walmart", "target", "starbucks", "shell", "chevron"))
        regular = (cadence != "custom" and len(ts) >= 3 and len(cycle_keys) >= 3 and confidence >= 0.82 and variation <= 0.10 and recent_enough and not forbidden_merchant)
        explicitly_confirmed = bool(learning and learning["decision"] == "confirm")
        if old and old.get("source") == "manual":
            status = old["status"]
        elif old and old["status"] in ("cancel_requested", "canceled"):
            status = old["status"]
        elif explicitly_confirmed:
            status = old["status"] if old and old["status"] == "active" else "active"
        else:
            status = "active" if regular else "candidate"
        if old and old.get("source") == "manual":
            payload = {"id": old["id"], "merchant": old["merchant"], "scope": old["scope"], "account_id": old["account_id"],
                       "amount": old["amount"], "cadence": old["cadence"], "custom_interval_days": old.get("custom_interval_days"),
                       "billing_day": old.get("billing_day"), "next_due": old.get("next_due"), "status": old["status"],
                       "confidence": old["confidence"], "reason": old["reason"], "management_url": old.get("management_url"),
                       "billing_channel": old.get("billing_channel"), "notes": old.get("notes", ""),
                       "observed_amount": old.get("observed_amount"), "price_review": old.get("price_review", 0), "ignored_price": old.get("ignored_price"),
                       "last_seen": ts[-1]["day"].isoformat(), "source": "manual"}
            observed_amount = round(ts[-1]["amount"], 2)
            meaningful_change = abs(float(old["amount"]) - observed_amount) > max(0.5, float(old["amount"]) * 0.10)
            already_ignored = old.get("ignored_price") is not None and abs(float(old["ignored_price"]) - observed_amount) <= 0.01
            if abs(float(old["amount"]) - observed_amount) <= 0.01:
                payload["observed_amount"] = None
                payload["price_review"] = 0
                payload["ignored_price"] = None
            elif old["status"] in ("active", "cancel_requested") and meaningful_change and not already_ignored:
                payload["observed_amount"] = observed_amount
                payload["price_review"] = 1
                payload["reason"] = f"Observed charge changed from ${float(old['amount']):.2f} to ${observed_amount:.2f}; review price change"
        else:
            payload = {"id": old["id"] if old else None, "merchant": ts[-1]["merchant"], "scope": ts[-1]["scope"], "account_id": ts[-1]["account_id"], "amount": amount, "cadence": cadence, "custom_interval_days": custom_days, "billing_day": ts[0]["day"].day, "status": status, "confidence": confidence, "reason": reason, "last_seen": ts[-1]["day"].isoformat(), "source": old.get("source", "detected") if old else "detected"}
            if old:
                payload.update({"observed_amount": old.get("observed_amount"), "price_review": old.get("price_review", 0), "ignored_price": old.get("ignored_price")})
                old_amount = float(old["amount"])
                change_floor = max(0.5, old_amount * 0.10)
                # Only the newest chronological charge is new price evidence.
                # Older charges remain historical evidence and must not cause
                # a prompt to return after the owner accepts a new price.
                observed = round(ts[-1]["amount"], 2)
                meaningful_change = abs(old_amount - observed) > change_floor
                already_ignored = old.get("ignored_price") is not None and abs(float(old["ignored_price"]) - observed) <= 0.01
                # A detected active subscription is already a known
                # commitment.  Keep it in the plan while a materially
                # different observed price is waiting for the same review
                # decision used by manual subscriptions.
                price_review_eligible = (cadence != "custom" and len(cycle_keys) >= 3 and recent_enough and not forbidden_merchant)
                current_price_is_known = abs(old_amount - observed) <= 0.01
                if old["status"] in ("active", "cancel_requested") and price_review_eligible and (meaningful_change or current_price_is_known):
                    payload["amount"] = old_amount
                    payload["status"] = old["status"]
                    if meaningful_change and not already_ignored:
                        payload["observed_amount"] = observed
                        payload["price_review"] = 1
                        payload["ignored_price"] = None
                        payload["reason"] = f"Observed charge changed from ${old_amount:.2f} to ${observed:.2f}; review price change"
                    else:
                        payload["observed_amount"] = None
                        payload["price_review"] = 0
                elif old["status"] in ("active", "cancel_requested") and already_ignored and price_review_eligible:
                    payload["amount"] = old_amount
                    payload["status"] = old["status"]
                    payload["observed_amount"] = None
                    payload["price_review"] = 0

        # Manual records own their billing anchor and amount; rescans only
        # update observed evidence around them.
        if not old or old.get("source") != "manual": payload["next_due"] = next_due.isoformat() if next_due else None
        record = save(payload)
        record["transaction_count"] = len(ts); record["amount_variation"] = round(variation, 3)
        found.append(record)
    return {"items": [x for x in found if x["status"] == "active"], "candidates": [x for x in found if x["status"] == "candidate"], "scanned": len(rows)}


def listing(scope=None):
    init_schema()
    where, args = ["status NOT IN ('dismissed')"], []
    if scope:
        if scope not in ("business", "personal"): raise ValueError("scope must be business or personal")
        where.append("scope=?"); args.append(scope)
    rows = [_row(r) for r in db.q("SELECT * FROM subscriptions WHERE " + " AND ".join(where) + " ORDER BY next_due IS NULL,next_due,merchant", args)]
    active = [r for r in rows if r["status"] in ("active", "cancel_requested")]
    candidates = [r for r in rows if r["status"] == "candidate"]
    price_reviews = [r for r in active if r.get("price_review")]
    return {"items": active, "candidates": candidates, "monthly_total": round(sum(r["monthly_equivalent"] for r in active), 2),
            "business_monthly": round(sum(r["monthly_equivalent"] for r in active if r["scope"] == "business"), 2),
            "personal_monthly": round(sum(r["monthly_equivalent"] for r in active if r["scope"] == "personal"), 2),
            "canceled": [r for r in rows if r["status"] == "canceled"], "price_reviews": price_reviews}


def review(subscription_id, decision):
    init_schema()
    if decision not in DECISIONS: raise ValueError("unsupported subscription review decision")
    row = db.q1("SELECT * FROM subscriptions WHERE id=?", (subscription_id,))
    if not row: raise ValueError("subscription not found")
    if decision in ("accept_price", "keep_price"):
        if not row.get("price_review") or row.get("observed_amount") is None:
            raise ValueError("subscription has no pending price review")
        now = _now()
        observed = float(row["observed_amount"])
        if decision == "accept_price":
            db.ex("UPDATE subscriptions SET amount=?,observed_amount=NULL,price_review=0,ignored_price=NULL,updated_at=? WHERE id=?", (observed, now, subscription_id))
        else:
            db.ex("UPDATE subscriptions SET observed_amount=?,price_review=0,ignored_price=?,updated_at=? WHERE id=?", (observed, observed, now, subscription_id))
        db.ex("INSERT INTO subscription_reviews(subscription_id,decision,created_at) VALUES(?,?,?)", (subscription_id, decision, now))
        return _row(db.q1("SELECT * FROM subscriptions WHERE id=?", (subscription_id,)))
    status = "active" if decision in ("confirm", "activate") else "dismissed" if decision == "dismiss" else "canceled"
    now = _now()
    db.ex("UPDATE subscriptions SET status=?,updated_at=? WHERE id=?", (status, now, subscription_id))
    db.ex("INSERT INTO subscription_reviews(subscription_id,decision,created_at) VALUES(?,?,?)", (subscription_id, decision, now))
    db.ex("INSERT INTO subscription_learning(normalized_key,decision,updated_at) VALUES(?,?,?) ON CONFLICT(normalized_key) DO UPDATE SET decision=excluded.decision,updated_at=excluded.updated_at", (row["normalized_key"], "dismiss" if decision == "dismiss" else "confirm", now))
    return _row(db.q1("SELECT * FROM subscriptions WHERE id=?", (subscription_id,)))


def _matches(sub, tx):
    if sub["scope"] != tx["scope"]: return False
    if sub["account_id"] and tx.get("account_id") != sub["account_id"]: return False
    a, b = _norm(sub["merchant"]), _norm(tx.get("merchant") or tx.get("name"))
    if a != b: return False
    expected_amount = sub.get("observed_amount") if sub.get("price_review") and sub.get("observed_amount") is not None else sub.get("amount")
    return _amount_close(expected_amount, tx.get("amount"))


def monthly_plan(scope=None, month=None):
    init_schema()
    if scope and scope not in ("business", "personal"): raise ValueError("scope must be business or personal")
    try:
        if month and not re.fullmatch(r"\d{4}-\d{2}", str(month)):
            raise ValueError
        first = date.fromisoformat(str(month) + "-01") if month else date.today().replace(day=1)
    except ValueError: raise ValueError("month must be YYYY-MM")
    last = date(first.year + (first.month == 12), (first.month % 12) + 1, 1)
    transfer_clause = " AND COALESCE(is_transfer,0)=0" if _has_column("transactions", "is_transfer") else ""
    has_pending = _has_column("transactions", "pending")
    date_clause = " AND (posted<=? OR COALESCE(pending,0)=1)" if has_pending else " AND posted<=?"
    args = [first.isoformat(), last.isoformat(), date.today().isoformat()]; where = "amount<0 AND posted>=? AND posted<?" + date_clause + transfer_clause
    if scope: where += " AND scope=?"; args.append(scope)
    txs = db.q("SELECT * FROM transactions WHERE " + where, args)
    spent = round(sum(abs(float(t["amount"])) for t in txs if not t.get("pending")), 2)
    pending_spend = round(sum(abs(float(t["amount"])) for t in txs if t.get("pending")), 2)
    active = db.q("SELECT * FROM subscriptions WHERE status IN ('active','cancel_requested')" + (" AND scope=?" if scope else ""), (scope,) if scope else ())
    upcoming, paid = [], []
    used_tx_ids = set()
    for sub in active:
        due = _parse_day(sub.get("next_due")) or first
        anchor = sub.get("billing_day") or due.day
        while due < first: due = _add_due(due, sub["cadence"], anchor_day=anchor, custom_interval_days=sub.get("custom_interval_days")) or (due + timedelta(days=30))
        while due < last:
            matched = next((t for t in txs if t["id"] not in used_tx_ids and _matches(sub, t) and abs((_parse_day(t["posted"]) - due).days) <= max(3, round(CADENCES.get(sub["cadence"], sub.get("custom_interval_days") or 30) * .2))), None)
            item = {**_row(sub), "due": due.isoformat(), "expected": round(float(sub["amount"]), 2)}
            if matched: item["transaction_id"] = matched["id"]; used_tx_ids.add(matched["id"]); paid.append(item)
            else: upcoming.append(item)
            due = _add_due(due, sub["cadence"], anchor_day=anchor, custom_interval_days=sub.get("custom_interval_days")) or (due + timedelta(days=30))
    upcoming.sort(key=lambda item: (item.get("due") or "", item.get("merchant") or "", item.get("id") or ""))
    paid.sort(key=lambda item: (item.get("due") or "", item.get("merchant") or "", item.get("id") or ""))
    # Pending charges are already committed money, but are not yet part of
    # posted spend. Include them once in the forecast and suppress their
    # matching predicted renewal above.
    expected = round(spent + pending_spend + sum(x["expected"] for x in upcoming), 2)
    monthly_total = sum((float(s["amount"]) * 365.25 / 12 / float(s["custom_interval_days"])) if s["cadence"] == "custom" and s.get("custom_interval_days") else _monthly(float(s["amount"]), s["cadence"]) for s in active)
    return {"spent": spent, "pending_spend": pending_spend, "upcoming": round(sum(x["expected"] for x in upcoming), 2), "total_expected": expected,
            "monthly_subscriptions": round(monthly_total, 2),
            "upcoming_items": upcoming, "paid_items": paid}
