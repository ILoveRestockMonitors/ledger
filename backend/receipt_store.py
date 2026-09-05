"""Local receipt enrichment queue and item allocation persistence.

Receipt lookup is deliberately a worker boundary.  This module never logs in
to a provider or opens a browser; it stores bounded, reviewable proposals and
applies only allocations which reconcile exactly to the bank transaction.
"""
import hashlib
import json
import math
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlparse

import db


JOB_STATUSES = ("queued", "running", "needs_user", "review", "applied", "dismissed", "failed")
DECISIONS = ("accept", "dismiss")


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _id(prefix):
    return prefix + "_" + uuid.uuid4().hex[:16]


def _json(value):
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _loads(value, default=None):
    if not value:
        return default
    try:
        result = json.loads(value)
        return result if result is not None else default
    except (TypeError, ValueError):
        return default


def _cents(value):
    # Stored transaction amounts are already rounded to cents.  Avoid a
    # float-based tolerance here: receipt allocations must reconcile exactly.
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("transaction amount is not valid money")
    return int(abs(amount) * 100)


def financial_fingerprint(tx):
    """Stable identity of the bank facts that make a receipt match valid."""
    values = [tx.get("account_id"), tx.get("scope"), tx.get("amount"),
              tx.get("posted"), int(bool(tx.get("pending"))),
              int(bool(tx.get("is_transfer")))]
    return hashlib.sha256("|".join("" if v is None else str(v) for v in values).encode()).hexdigest()


def init_schema():
    """Create receipt jobs and allocations. Safe to call during every startup."""
    c = db._conn()
    try:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS receipt_jobs (
          id TEXT PRIMARY KEY,
          transaction_id TEXT NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
          provider TEXT NOT NULL CHECK(provider IN ('amazon','apple','google')),
          status TEXT NOT NULL CHECK(status IN ('queued','running','needs_user','review','applied','dismissed','failed')),
          payload TEXT,
          proposal TEXT,
          message TEXT DEFAULT '',
          source_fingerprint TEXT,
          verified INTEGER NOT NULL DEFAULT 0,
          receipt_order_id TEXT,
          original_category_id TEXT,
          original_category_override INTEGER,
          attempts INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_receipt_jobs_tx ON receipt_jobs(transaction_id, updated_at);
        CREATE INDEX IF NOT EXISTS idx_receipt_jobs_status ON receipt_jobs(status, created_at);
        CREATE TABLE IF NOT EXISTS receipt_attempts (
          id TEXT PRIMARY KEY,
          job_id TEXT NOT NULL REFERENCES receipt_jobs(id) ON DELETE CASCADE,
          attempted_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_receipt_attempts_day ON receipt_attempts(attempted_at);
        CREATE TABLE IF NOT EXISTS receipt_allocations (
          id TEXT PRIMARY KEY,
          job_id TEXT NOT NULL REFERENCES receipt_jobs(id) ON DELETE CASCADE,
          transaction_id TEXT NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
          line_key TEXT NOT NULL,
          description TEXT NOT NULL,
          amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
          category_id TEXT REFERENCES categories(id),
          confidence REAL,
          manual_category INTEGER NOT NULL DEFAULT 0,
          manual_amount INTEGER NOT NULL DEFAULT 0,
          active INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(job_id, line_key)
        );
        CREATE INDEX IF NOT EXISTS idx_receipt_alloc_tx ON receipt_allocations(transaction_id, active);
        """)
        cols = {r[1] for r in c.execute("PRAGMA table_info(receipt_jobs)")}
        if "verified" not in cols:
            c.execute("ALTER TABLE receipt_jobs ADD COLUMN verified INTEGER NOT NULL DEFAULT 0")
        if "receipt_order_id" not in cols:
            c.execute("ALTER TABLE receipt_jobs ADD COLUMN receipt_order_id TEXT")
        if "original_category_id" not in cols:
            c.execute("ALTER TABLE receipt_jobs ADD COLUMN original_category_id TEXT")
        if "original_category_override" not in cols:
            c.execute("ALTER TABLE receipt_jobs ADD COLUMN original_category_override INTEGER")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_receipt_order ON receipt_jobs(provider,receipt_order_id) WHERE receipt_order_id IS NOT NULL AND receipt_order_id <> ''")
        c.commit()
    finally:
        c.close()


def _ensure():
    # Tests and small callers often initialize db directly without invoking
    # server startup.  init_schema is idempotent and cheap in SQLite.
    init_schema()


def detect_provider(tx):
    """Return a supported provider for a conservative merchant/name match."""
    text = " ".join(str(tx.get(k) or "") for k in ("merchant", "name")).upper()
    if any(token in text for token in ("AMAZON", "AMZN", "AMAZON.COM", "AMAZON MKTPLACE")):
        return "amazon"
    if any(token in text for token in ("APPLE.COM/BILL", "APPLE.COM", "ITUNES.COM", "APPLE SERVICES")):
        return "apple"
    if any(token in text for token in ("GOOGLE *", "GOOGLE PLAY", "GOOGLE.COM", "GOOGLE STORAGE")):
        return "google"
    return None


def _tx(conn, transaction_id):
    row = conn.execute("""SELECT t.*, a.iso_currency, a.mask account_mask, a.archived account_archived,
                                 i.env item_env
                          FROM transactions t LEFT JOIN accounts a ON a.id=t.account_id
                          LEFT JOIN items i ON i.id=a.item_id
                          WHERE t.id=?""", (transaction_id,)).fetchone()
    if not row:
        raise ValueError("transaction not found")
    return dict(row)


def _eligible(tx):
    if tx.get("pending") or tx.get("is_transfer") or float(tx.get("amount") or 0) >= 0:
        raise ValueError("receipt lookup requires a posted expense")
    try:
        posted = date.fromisoformat(str(tx.get("posted")))
    except (TypeError, ValueError):
        raise ValueError("receipt lookup requires a valid transaction date")
    if posted > datetime.now().date():
        raise ValueError("receipt lookup cannot use a future transaction")
    if tx.get("account_archived"):
        raise ValueError("receipt lookup is unavailable for archived accounts")
    if tx.get("item_env") in ("demo", "sandbox"):
        raise ValueError("receipt lookup is unavailable for demo or sandbox items")


def _public_job(row):
    if not row:
        return None
    result = {k: row[k] for k in ("id", "transaction_id", "provider", "status", "message", "attempts", "verified", "receipt_order_id", "created_at", "updated_at") if k in row.keys()}
    if "verified" in result:
        result["verified"] = bool(result["verified"])
    result["proposal"] = _loads(row["proposal"], None)
    result["payload"] = _loads(row["payload"], None)
    result["can_apply"] = bool(result.get("verified") and result.get("status") in ("review", "needs_user"))
    if "amount" in row.keys():
        result["transaction"] = {
            "id": row["transaction_id"], "amount": row["amount"],
            "posted": row["posted"], "name": row["name"],
            "merchant": row["merchant"], "scope": row["scope"],
            "account_id": row["account_id"],
            "currency": row["iso_currency"] or db.get_config().get("currency", "USD"),
            "mask": row["account_mask"],
        }
    return result


def _validate_payload(payload, tx, *, require_items=False):
    if not isinstance(payload, dict):
        raise ValueError("receipt payload must be an object")
    status = payload.get("status")
    if status not in ("matched", "needs_user", "failed"):
        raise ValueError("receipt status is invalid")
    message = str(payload.get("message") or "")[:2000]
    proposal = payload.get("proposal") or {}
    if not isinstance(proposal, dict):
        raise ValueError("receipt proposal must be an object")
    items = proposal.get("items") or []
    if not isinstance(items, list):
        raise ValueError("receipt items must be a list")
    if len(items) > 100:
        raise ValueError("receipt has too many items")
    if "receipt" in proposal and proposal.get("receipt") is not None and not isinstance(proposal.get("receipt"), dict):
        raise ValueError("receipt evidence must be an object")
    if "match_confidence" in proposal:
        confidence = proposal["match_confidence"]
        if type(confidence) not in (int, float) or isinstance(confidence, bool) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("match_confidence must be finite and between 0 and 1")
    if require_items or status == "matched":
        expected = _cents(tx["amount"])
        total = 0
        clean = []
        seen = set()
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError("receipt item must be an object")
            if not isinstance(item.get("description"), str):
                raise ValueError("receipt item needs a text description")
            description = item["description"].strip()
            if len(description) > 300:
                raise ValueError("receipt item description is too long")
            if not description:
                raise ValueError("receipt item needs a description")
            if type(item.get("amount_cents")) is not int:
                raise ValueError("receipt item amount_cents must be an integer")
            cents = item["amount_cents"]
            if cents <= 0:
                raise ValueError("receipt item amount must be positive")
            confidence = item.get("confidence")
            if confidence is not None and (type(confidence) not in (int, float) or isinstance(confidence, bool) or not math.isfinite(confidence) or not 0 <= confidence <= 1):
                raise ValueError("item confidence must be finite and between 0 and 1")
            key = str(item.get("line_key") or index)
            if key in seen:
                raise ValueError("receipt item line_key must be unique")
            seen.add(key)
            category_id = item.get("category_id")
            if category_id:
                category = db.q1("SELECT id,kind FROM categories WHERE id=?", (category_id,))
                if not category or category["kind"] != "expense":
                    raise ValueError("receipt item category is invalid")
            total += cents
            clean.append({
                "line_key": key, "description": description,
                "amount_cents": cents, "category_id": category_id,
                "confidence": item.get("confidence"),
            })
        if total != expected:
            raise ValueError("receipt allocations must equal the bank charge exactly")
        receipt = proposal.get("receipt") or {}
        if receipt.get("url") is not None and (not isinstance(receipt["url"], str) or urlparse(receipt["url"]).scheme != "https"):
            raise ValueError("receipt URL must use https")
        if receipt.get("purchased_on") is not None:
            try:
                purchased = date.fromisoformat(str(receipt["purchased_on"]))
            except (TypeError, ValueError):
                raise ValueError("receipt purchased_on must be YYYY-MM-DD")
        if receipt.get("currency") is not None and (not isinstance(receipt["currency"], str) or len(receipt["currency"]) != 3 or not receipt["currency"].isalpha()):
            raise ValueError("receipt currency must be a three-letter code")
        if receipt.get("total_cents") is not None and (type(receipt["total_cents"]) is not int or receipt["total_cents"] != expected):
            raise ValueError("receipt total does not equal the bank charge")
        if receipt.get("card_last4") is not None and (not isinstance(receipt["card_last4"], str) or not receipt["card_last4"].isdigit() or len(receipt["card_last4"]) != 4):
            raise ValueError("receipt card_last4 must contain four digits")
        if len(str(receipt.get("order_id") or "")) > 200:
            raise ValueError("receipt order_id is too long")
        if proposal.get("description") is not None and not isinstance(proposal.get("description"), str):
            raise ValueError("receipt description must be text")
        if len(str(proposal.get("description") or "")) > 300:
            raise ValueError("receipt description is too long")
        proposal = dict(proposal)
        proposal["items"] = clean
    proposal.setdefault("items", items)
    return {"status": status, "message": message, "proposal": proposal}


def _latest_job(conn, transaction_id):
    return conn.execute("SELECT * FROM receipt_jobs WHERE transaction_id=? ORDER BY updated_at DESC, created_at DESC, rowid DESC LIMIT 1", (transaction_id,)).fetchone()


def _active_job(conn, transaction_id):
    return conn.execute("SELECT * FROM receipt_jobs WHERE transaction_id=? AND status='applied' ORDER BY updated_at DESC, rowid DESC LIMIT 1", (transaction_id,)).fetchone()


def _daily_used(conn):
    today = datetime.now().date().isoformat()
    row = conn.execute("SELECT COUNT(*) n FROM receipt_attempts WHERE attempted_at>=?", (today,)).fetchone()
    return int(row["n"] or 0)


def _queue(conn, tx, provider, *, force=False):
    existing = _latest_job(conn, tx["id"])
    if existing and not force and existing["status"] in ("queued", "running", "needs_user", "review", "applied"):
        return existing
    now = _now()
    jid = _id("receipt")
    conn.execute("""INSERT INTO receipt_jobs(id,transaction_id,provider,status,message,source_fingerprint,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?)""", (jid, tx["id"], provider, "queued", "", financial_fingerprint(tx), now, now))
    return conn.execute("SELECT * FROM receipt_jobs WHERE id=?", (jid,)).fetchone()


def request(transaction_id):
    _ensure()
    c = db._conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        tx = _tx(c, transaction_id)
        _eligible(tx)
        provider = detect_provider(tx)
        if not provider:
            raise ValueError("transaction merchant is not a supported receipt provider")
        limit = max(0, int(db.get_config().get("receipt_daily_limit", 10) or 0))
        existing = _latest_job(c, transaction_id)
        if not existing and _daily_used(c) >= limit:
            raise ValueError("daily receipt lookup limit reached")
        row = _queue(c, tx, provider)
        c.commit()
        return _public_job(row)
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def scan():
    _ensure()
    cfg = db.get_config()
    if not cfg.get("receipt_lookup_enabled", False):
        return {"queued": 0, "disabled": True}
    limit = max(0, int(cfg.get("receipt_daily_limit", 10) or 0))
    c = db._conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        used = _daily_used(c)
        rows = c.execute("""SELECT t.*,a.archived account_archived,i.env item_env
                            FROM transactions t LEFT JOIN accounts a ON a.id=t.account_id
                            LEFT JOIN items i ON i.id=a.item_id
                            WHERE t.amount<0 AND t.pending=0 AND t.is_transfer=0
                              AND t.posted<=date('now','localtime')
                            ORDER BY t.posted DESC, t.id""").fetchall()
        queued = 0
        for row in rows:
            if used >= limit:
                break
            tx = dict(row)
            try:
                _eligible(tx)
            except ValueError:
                continue
            provider = detect_provider(tx)
            if not provider or _latest_job(c, tx["id"]):
                continue
            _queue(c, tx, provider)
            used += 1
            queued += 1
        c.commit()
        return {"queued": queued, "disabled": False, "daily_limit": limit}
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def claim_next():
    _ensure()
    c = db._conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        c.execute("UPDATE receipt_jobs SET status='queued',updated_at=? WHERE status='running' AND julianday(updated_at) < julianday('now','localtime','-30 minutes')", (_now(),))
        limit = max(0, int(db.get_config().get("receipt_daily_limit", 10) or 0))
        if _daily_used(c) >= limit:
            c.commit()
            return None
        row = c.execute("SELECT j.*,t.amount,t.posted,t.name,t.merchant,t.scope,t.account_id,t.pending,t.is_transfer,a.iso_currency,a.mask account_mask FROM receipt_jobs j JOIN transactions t ON t.id=j.transaction_id LEFT JOIN accounts a ON a.id=t.account_id WHERE j.status='queued' ORDER BY j.created_at LIMIT 1").fetchone()
        if not row:
            c.commit()
            return None
        tx = _tx(c, row["transaction_id"])
        try:
            _eligible(tx)
        except ValueError as exc:
            c.execute("UPDATE receipt_jobs SET status='failed',message=?,updated_at=? WHERE id=?", (str(exc), _now(), row["id"]))
            c.commit()
            return None
        now = _now()
        c.execute("INSERT INTO receipt_attempts(id,job_id,attempted_at) VALUES(?,?,?)", (_id("attempt"), row["id"], now))
        c.execute("UPDATE receipt_jobs SET status='running', attempts=attempts+1, updated_at=? WHERE id=?", (now, row["id"]))
        result = dict(row)
        result.update({"status": "running", "attempts": int(row["attempts"] or 0) + 1, "updated_at": now, "fingerprint": financial_fingerprint(tx), "currency": tx.get("iso_currency") or db.get_config().get("currency", "USD"), "transaction": {"id": tx["id"], "amount": tx["amount"], "posted": tx["posted"], "name": tx["name"], "merchant": tx["merchant"], "scope": tx["scope"], "account_id": tx["account_id"], "currency": tx.get("iso_currency") or db.get_config().get("currency", "USD"), "mask": tx.get("account_mask")}})
        c.commit()
        return result
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def _apply(c, job, proposal, *, require_categories=False, manual_categories=False):
    tx = _tx(c, job["transaction_id"])
    if financial_fingerprint(tx) != job["source_fingerprint"]:
        c.execute("UPDATE receipt_jobs SET status='review', message=?, updated_at=? WHERE id=?", ("Bank transaction changed; receipt needs review.", _now(), job["id"]))
        raise ValueError("bank transaction changed since receipt lookup")
    clean = _validate_payload({"status": "matched", "proposal": proposal}, tx, require_items=True)["proposal"]
    if require_categories and any(not item.get("category_id") for item in clean["items"]):
        raise ValueError("choose a category for every receipt item before accepting")
    if not _receipt_identity_matches(clean.get("receipt") or {}, tx):
        raise ValueError("receipt identity does not match the account or transaction")
    order_id = str((clean.get("receipt") or {}).get("order_id") or "")
    duplicate = c.execute("SELECT id FROM receipt_jobs WHERE provider=? AND receipt_order_id=? AND id<>?", (job["provider"], order_id, job["id"])).fetchone()
    if duplicate:
        raise ValueError("receipt order is already attached to another transaction")
    c.execute("UPDATE receipt_allocations SET active=0, updated_at=? WHERE transaction_id=?", (_now(), tx["id"]))
    now = _now()
    for item in clean["items"]:
        c.execute("""INSERT INTO receipt_allocations(id,job_id,transaction_id,line_key,description,amount_cents,category_id,confidence,manual_category,created_at,updated_at)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (_id("alloc"), job["id"], tx["id"], item["line_key"], item["description"], item["amount_cents"], item.get("category_id"), item.get("confidence"), int(bool(manual_categories)), now, now))
    # Child allocations become the explicit classification.  Keep the
    # original parent category in the job so undo can restore it.
    c.execute("UPDATE transactions SET category_override=NULL WHERE id=?", (tx["id"],))
    c.execute("UPDATE receipt_jobs SET status='applied',proposal=?,source_fingerprint=?,verified=1,receipt_order_id=?,original_category_id=?,original_category_override=?,message=?,updated_at=? WHERE id=?", (_json(clean), financial_fingerprint(tx), order_id, tx.get("category_id"), tx.get("category_override"), "Receipt applied.", now, job["id"]))


def _receipt_identity_matches(receipt, tx):
    try:
        if receipt.get("currency") and receipt["currency"].upper() != str(tx.get("iso_currency") or db.get_config().get("currency", "USD")).upper():
            return False
        if receipt.get("card_last4") and tx.get("account_mask") and receipt["card_last4"] != str(tx["account_mask"]):
            return False
        if receipt.get("purchased_on"):
            purchased = date.fromisoformat(str(receipt["purchased_on"]))
            posted = date.fromisoformat(str(tx["posted"]))
            if abs((purchased - posted).days) > 7:
                return False
        return True
    except (TypeError, ValueError):
        return False


def _high_confidence(proposal, tx):
    try:
        if tx.get("category_override"):
            return False
        receipt = proposal.get("receipt") or {}
        if any(not receipt.get(key) for key in ("url", "order_id", "purchased_on", "currency", "total_cents", "card_last4")):
            return False
        if not tx.get("account_mask"):
            return False
        if not _receipt_identity_matches(receipt, tx):
            return False
        return (not bool(proposal.get("ambiguous")) and float(proposal.get("match_confidence", 0)) >= .95
                and all(item.get("category_id") and float(item.get("confidence", 0)) >= .90 for item in proposal.get("items", [])))
    except (TypeError, ValueError):
        return False


def finish(job_id, payload, verified=False, expected_attempt=None):
    _ensure()
    c = db._conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        job = c.execute("SELECT * FROM receipt_jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            raise ValueError("receipt job not found")
        if job["status"] in ("applied", "dismissed"):
            c.commit()
            return _public_job(job)
        if expected_attempt is not None:
            if job["status"] != "running" or type(expected_attempt) is not int or job["attempts"] != expected_attempt:
                raise ValueError("receipt worker claim is stale")
        tx = _tx(c, job["transaction_id"])
        clean = _validate_payload(payload, tx)
        status = clean["status"]
        order_id = str((clean["proposal"].get("receipt") or {}).get("order_id") or "")
        duplicate_order = c.execute("SELECT id FROM receipt_jobs WHERE provider=? AND receipt_order_id=? AND id<>?", (job["provider"], order_id, job_id)).fetchone() if order_id else None
        if status == "matched" and verified and _high_confidence(clean["proposal"], tx) and db.get_config().get("receipt_auto_apply", True) and not duplicate_order:
            _apply(c, job, clean["proposal"])
        else:
            public_status = "review" if status == "matched" else ("needs_user" if status == "needs_user" else "failed")
            proposal = clean["proposal"]
            message = clean["message"] or ("Receipt requires review." if status == "matched" else "")
            order_id = str((proposal.get("receipt") or {}).get("order_id") or "")
            duplicate = c.execute("SELECT id FROM receipt_jobs WHERE provider=? AND receipt_order_id=? AND id<>?", (job["provider"], order_id, job_id)).fetchone() if order_id else None
            if duplicate:
                public_status, message = "needs_user", "Receipt order is already attached to another transaction."
                order_id = None
            c.execute("UPDATE receipt_jobs SET status=?,payload=?,proposal=?,verified=?,receipt_order_id=?,message=?,updated_at=? WHERE id=?", (public_status, _json(payload), _json(proposal), int(bool(verified)), order_id or None, message, _now(), job_id))
        c.commit()
        return _public_job(c.execute("SELECT * FROM receipt_jobs WHERE id=?", (job_id,)).fetchone())
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def resume(job_id):
    _ensure()
    c = db._conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT * FROM receipt_jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise ValueError("receipt job not found")
        if row["status"] not in ("needs_user", "failed", "review"):
            raise ValueError("receipt job cannot be resumed")
        c.execute("UPDATE receipt_jobs SET status='queued',updated_at=?,message='' WHERE id=?", (_now(), job_id))
        c.commit()
        return _public_job(c.execute("SELECT * FROM receipt_jobs WHERE id=?", (job_id,)).fetchone())
    finally:
        c.close()


def review(job_id, decision, category_ids=None):
    _ensure()
    if decision not in DECISIONS:
        raise ValueError("decision must be accept or dismiss")
    c = db._conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        job = c.execute("SELECT * FROM receipt_jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            raise ValueError("receipt job not found")
        if job["status"] in ("applied", "dismissed"):
            c.commit()
            return _public_job(job)
        if decision == "dismiss":
            c.execute("UPDATE receipt_allocations SET active=0,updated_at=? WHERE job_id=?", (_now(), job_id))
            c.execute("UPDATE receipt_jobs SET status='dismissed',receipt_order_id=NULL,message=?,updated_at=? WHERE id=?", ("Receipt dismissed.", _now(), job_id))
        else:
            if not job["verified"]:
                raise ValueError("receipt evidence has not passed trusted capture checks")
            proposal = _loads(job["proposal"], {})
            if category_ids is not None:
                if not isinstance(category_ids, list) or len(category_ids) != len(proposal.get("items") or []):
                    raise ValueError("category_ids must match receipt item count")
                proposal = dict(proposal)
                items = []
                for item, category_id in zip(proposal.get("items") or [], category_ids):
                    if not isinstance(category_id, str) or not c.execute("SELECT 1 FROM categories WHERE id=? AND kind='expense'", (category_id,)).fetchone():
                        raise ValueError("choose a valid expense category for every receipt item")
                    updated = dict(item)
                    updated["category_id"] = category_id
                    items.append(updated)
                proposal["items"] = items
            _apply(c, job, proposal, require_categories=True, manual_categories=category_ids is not None)
        c.commit()
        return _public_job(c.execute("SELECT * FROM receipt_jobs WHERE id=?", (job_id,)).fetchone())
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def undo(transaction_id):
    _ensure()
    c = db._conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        c.execute("UPDATE receipt_allocations SET active=0,updated_at=? WHERE transaction_id=?", (_now(), transaction_id))
        applied = c.execute("SELECT * FROM receipt_jobs WHERE transaction_id=? AND status='applied' ORDER BY updated_at DESC LIMIT 1", (transaction_id,)).fetchone()
        if applied:
            c.execute("UPDATE transactions SET category_id=?,category_override=? WHERE id=?", (applied["original_category_id"], applied["original_category_override"], transaction_id))
        c.execute("UPDATE receipt_jobs SET status='dismissed',receipt_order_id=NULL,message=?,updated_at=? WHERE transaction_id=? AND status='applied'", ("Receipt enrichment undone.", _now(), transaction_id))
        c.commit()
        return detail(transaction_id)
    finally:
        c.close()


def _allocation_rows(c, transaction_id):
    return [dict(r) for r in c.execute("""SELECT a.*,c.name cat_name FROM receipt_allocations a
                                         LEFT JOIN categories c ON c.id=a.category_id
                                         JOIN receipt_jobs j ON j.id=a.job_id
                                         WHERE a.transaction_id=? AND a.active=1 AND j.status='applied'
                                         ORDER BY a.rowid""", (transaction_id,)).fetchall()]


def allocation_map(transaction_ids):
    """Return active receipt allocations keyed by parent transaction ID.

    Consumers must count the parent for transaction counts and use these rows
    only for category amounts.  An absent key means the parent category is the
    fallback allocation.
    """
    _ensure()
    ids = [str(x) for x in transaction_ids if x]
    if not ids:
        return {}
    if len(ids) > 800:
        result = {}
        for start in range(0, len(ids), 800):
            result.update(allocation_map(ids[start:start + 800]))
        return result
    c = db._conn()
    try:
        marks = ",".join("?" for _ in ids)
        sql = ("SELECT a.transaction_id,a.description,a.amount_cents,a.category_id,a.manual_category,a.manual_amount,c.name cat_name,"
               "t.amount parent_amount,t.account_id,t.scope,t.posted,t.pending,t.is_transfer,t.category_override,j.source_fingerprint "
               "FROM receipt_allocations a JOIN receipt_jobs j ON j.id=a.job_id "
               "JOIN transactions t ON t.id=a.transaction_id LEFT JOIN categories c ON c.id=a.category_id "
               "WHERE a.transaction_id IN (" + marks + ") AND a.active=1 AND j.status='applied' "
               "ORDER BY a.transaction_id,a.rowid")
        rows = c.execute(sql, ids).fetchall()
        out = {}
        for row in rows:
            txid = row["transaction_id"]
            bucket = out.setdefault(txid, {"rows": [], "expected": _cents(row["parent_amount"]), "fingerprint": row["source_fingerprint"], "tx": dict(row)})
            bucket["rows"].append(dict(row))
        # Fail closed if a parent was edited without going through the helper
        # or if a previous migration left an incomplete allocation set.
        result = {}
        for txid, bucket in out.items():
            tx = bucket["tx"]
            tx["amount"] = tx.get("parent_amount")
            if bucket["fingerprint"] != financial_fingerprint(tx):
                continue
            if tx.get("pending") or tx.get("is_transfer") or tx.get("category_override") or float(tx.get("parent_amount") or 0) >= 0:
                continue
            try:
                if date.fromisoformat(str(tx.get("posted"))) > datetime.now().date():
                    continue
            except (TypeError, ValueError):
                continue
            if sum(int(item["amount_cents"]) for item in bucket["rows"]) != bucket["expected"]:
                continue
            for item in bucket["rows"]:
                for key in ("parent_amount", "account_id", "scope", "posted", "pending", "is_transfer", "category_override", "source_fingerprint"):
                    item.pop(key, None)
            result[txid] = bucket["rows"]
        return result
    finally:
        c.close()


def decorate_transactions(rows):
    _ensure()
    if not rows:
        return rows
    c = db._conn()
    try:
        ids = [row.get("id") for row in rows if row.get("id")]
        amap = allocation_map(ids)
        marks = ",".join("?" for _ in ids)
        job_rows = c.execute("SELECT * FROM receipt_jobs WHERE transaction_id IN (" + marks + ") ORDER BY updated_at DESC,created_at DESC,rowid DESC", ids).fetchall() if ids else []
        latest_by_tx = {}
        active_by_tx = {}
        for job in job_rows:
            latest_by_tx.setdefault(job["transaction_id"], job)
            if job["status"] == "applied":
                active_by_tx.setdefault(job["transaction_id"], job)
        for row in rows:
            tid = row.get("id")
            if not tid:
                row.update({"display_name": row.get("name"), "receipt_status": None, "receipt_job_id": None, "receipt_provider": None, "allocations": []})
                continue
            allocations = amap.get(tid, [])
            job = active_by_tx.get(tid) if tid in amap else None
            latest = latest_by_tx.get(tid)
            chosen = job or latest
            proposal = _loads(chosen["proposal"], {}) if chosen else {}
            description = proposal.get("description") if job and isinstance(proposal, dict) else None
            row.update({
                "display_name": description or (row.get("name") if row.get("name_override") else row.get("merchant") or row.get("name")),
                "receipt_status": "applied" if job else (latest["status"] if latest and latest["status"] != "applied" else None),
                "receipt_job_id": chosen["id"] if chosen and (job or latest["status"] != "applied") else None,
                "receipt_provider": chosen["provider"] if chosen and (job or latest["status"] != "applied") else detect_provider(row),
                "allocations": [{k: a.get(k) for k in ("description", "amount_cents", "category_id", "cat_name")} for a in allocations],
            })
        return rows
    finally:
        c.close()


def detail(transaction_id):
    _ensure()
    c = db._conn()
    try:
        tx = _tx(c, transaction_id)
        job = _latest_job(c, transaction_id)
        return {"transaction": tx, "job": _public_job(job), "allocations": allocation_map([transaction_id]).get(transaction_id, []), "provider": detect_provider(tx)}
    finally:
        c.close()


def listing():
    _ensure()
    c = db._conn()
    try:
        rows = c.execute("""SELECT j.*,t.amount,t.posted,t.name,t.merchant,t.scope,t.account_id,
                                   a.iso_currency,a.mask account_mask
                            FROM receipt_jobs j JOIN transactions t ON t.id=j.transaction_id
                            LEFT JOIN accounts a ON a.id=t.account_id
                            ORDER BY j.updated_at DESC,j.created_at DESC""").fetchall()
        jobs = [_public_job(row) for row in rows]
        known = {j["transaction_id"] for j in jobs}
        candidates = []
        for row in c.execute("""SELECT t.*,a.iso_currency,a.mask account_mask,a.archived account_archived,i.env item_env
                                FROM transactions t LEFT JOIN accounts a ON a.id=t.account_id
                                LEFT JOIN items i ON i.id=a.item_id
                                WHERE t.amount<0 AND t.pending=0 AND t.is_transfer=0 AND t.posted<=date('now','localtime')"""):
            tx = dict(row)
            if tx["id"] in known or tx.get("account_archived") or tx.get("item_env") in ("demo", "sandbox"):
                continue
            provider = detect_provider(tx)
            if provider:
                candidates.append({"transaction": {"id": tx["id"], "amount": tx["amount"], "posted": tx["posted"], "name": tx["name"], "merchant": tx["merchant"], "scope": tx["scope"], "account_id": tx["account_id"], "currency": tx["iso_currency"] or db.get_config().get("currency", "USD"), "mask": tx["account_mask"]}, "provider": provider})
        return {"jobs": jobs, "candidates": candidates}
    finally:
        c.close()


def invalidate_transaction(transaction_id, conn=None):
    """Invalidate accepted receipt allocations after a bank fact changes.

    Called by the Plaid upsert while its transaction is still in the same SQL
    transaction.  The parent remains untouched and therefore still counts in
    cash flow exactly once.
    """
    own = conn is None
    c = conn or db._conn()
    try:
        row = c.execute("SELECT * FROM transactions WHERE id=?", (transaction_id,)).fetchone()
        if not row:
            return False
        try:
            jobs = c.execute("SELECT * FROM receipt_jobs WHERE transaction_id=? AND status='applied'", (transaction_id,)).fetchall()
        except Exception as exc:
            if "no such table" in str(exc).lower():
                return False
            raise
        changed = False
        fp = financial_fingerprint(dict(row))
        for job in jobs:
            if job["source_fingerprint"] and job["source_fingerprint"] != fp:
                c.execute("UPDATE receipt_allocations SET active=0,updated_at=? WHERE job_id=?", (_now(), job["id"]))
                c.execute("UPDATE receipt_jobs SET status='review',message=?,updated_at=? WHERE id=?", ("Bank transaction changed; receipt needs review.", _now(), job["id"]))
                changed = True
        if own:
            c.commit()
        return changed
    finally:
        if own:
            c.close()


def manual_update(transaction_id, patch):
    """Apply editable transaction fields and record category/name overrides.

    Server can call this helper from its existing transaction edit route.
    Unknown fields are rejected so receipt enrichment cannot become an SQL
    update escape hatch.
    """
    _ensure()
    allowed = {"category_id", "name", "note", "scope", "recurring", "is_transfer"}
    if not isinstance(patch, dict) or any(k not in allowed for k in patch):
        raise ValueError("unsupported transaction edit")
    if "name" in patch and (not isinstance(patch["name"], str) or len(patch["name"]) > 300):
        raise ValueError("name is too long")
    if "note" in patch and (not isinstance(patch["note"], str) or len(patch["note"]) > 2000):
        raise ValueError("note is too long")
    c = db._conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        _tx(c, transaction_id)
        fields, args = [], []
        for key, value in patch.items():
            if key == "category_id" and value:
                if not c.execute("SELECT 1 FROM categories WHERE id=?", (value,)).fetchone():
                    raise ValueError("category not found")
            if key == "scope" and value not in ("personal", "business"):
                raise ValueError("scope must be personal or business")
            if key in ("recurring", "is_transfer"):
                if isinstance(value, bool):
                    value = int(value)
                if type(value) is not int or value not in (0, 1):
                    raise ValueError(key + " must be a boolean")
            fields.append(key + "=?"); args.append(value)
            if key == "category_id":
                fields.append("category_override=1")
            if key == "scope":
                fields.append("scope_override=?"); args.append(value)
            if key == "is_transfer":
                if type(value) is not int or value not in (0, 1):
                    raise ValueError("is_transfer must be 0 or 1")
                fields.append("is_transfer_override=?"); args.append(value)
            if key == "name":
                fields.append("name_override=1")
        if fields:
            args.append(transaction_id)
            c.execute("UPDATE transactions SET " + ",".join(fields) + " WHERE id=?", args)
            if "category_id" in patch:
                c.execute("UPDATE receipt_allocations SET active=0,updated_at=? WHERE transaction_id=?", (_now(), transaction_id))
                c.execute("UPDATE receipt_jobs SET status='dismissed',receipt_order_id=NULL,message=?,updated_at=? WHERE transaction_id=? AND status='applied'", ("Receipt itemization superseded by a manual category.", _now(), transaction_id))
            if any(key in patch for key in ("scope", "is_transfer")):
                invalidate_transaction(transaction_id, conn=c)
        c.commit()
        return db.q1("SELECT * FROM transactions WHERE id=?", (transaction_id,))
    finally:
        c.close()
