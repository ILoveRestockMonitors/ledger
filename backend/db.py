"""SQLite persistence for Ledger.

Schema covers: items (Plaid connections), accounts (with business/personal
scope), transactions (with scope, category, notes, recurring flag), budgets,
goals, and app config.
"""
import json
import os
import sqlite3
import tempfile
import threading
from datetime import date

DATA_DIR = os.path.abspath(os.environ.get("LEDGER_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")))
DB_PATH = os.path.join(DATA_DIR, "ledger.db")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")

DEFAULT_CONFIG = {
    "plaid_client_id": "",
    "plaid_secret": "",
    "plaid_env": "sandbox",          # sandbox | production
    "currency": "USD",
    "theme": "light",
    "accent": "blue",
    "density": "comfortable",
    "font_family": "lora",
    "palette": "paper",
    "home_cards": ["recent", "upcoming", "cashflow", "goals"],
    "monthly_spending_target": 0,
    "plaid_redirect_uri": "",
    "sync_interval_minutes": 240,
    "owner_name": "",
    "start_of_month_day": 1,
    "tax_rate_business": 0.253,      # rough set-aside estimate
    "receipt_lookup_enabled": False,
    "receipt_auto_apply": True,
    "receipt_daily_limit": 10,
}


def _conn():
    os.makedirs(DATA_DIR, mode=0o700, exist_ok=True)
    os.chmod(DATA_DIR, 0o700)
    c = sqlite3.connect(DB_PATH, timeout=30)
    os.chmod(DB_PATH, 0o600)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def get_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg


_config_lock = threading.RLock()

def public_config():
    cfg = get_config()
    cfg["plaid_client_id_saved"] = bool(str(cfg.get("plaid_client_id") or "").strip())
    cfg["plaid_secret_saved"] = bool(str(cfg.get("plaid_secret") or "").strip())
    cfg["plaid_configured"] = cfg["plaid_client_id_saved"] and cfg["plaid_secret_saved"]
    cfg.pop("plaid_secret", None)
    cfg["plaid_client_id"] = ""
    return cfg

def save_config(patch):
    with _config_lock:
        os.makedirs(DATA_DIR, mode=0o700, exist_ok=True)
        cfg = get_config()
        clean = {k: v for k, v in patch.items() if k in DEFAULT_CONFIG}
        for key in ("plaid_client_id", "plaid_secret"):
            if not clean.get(key): clean.pop(key, None)
        cfg.update(clean)
        fd, tmp = tempfile.mkstemp(dir=DATA_DIR, prefix="config-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
                f.flush(); os.fsync(f.fileno())
            os.replace(tmp, CONFIG_PATH)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
        return public_config()


SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  id            TEXT PRIMARY KEY,
  plaid_item_id TEXT,
  institution   TEXT NOT NULL,
  env           TEXT NOT NULL DEFAULT 'demo',
  access_token  TEXT,
  cursor        TEXT,
  created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
  id             TEXT PRIMARY KEY,
  item_id        TEXT REFERENCES items(id) ON DELETE CASCADE,
  name           TEXT NOT NULL,
  official_name  TEXT,
  type           TEXT,
  subtype        TEXT,
  scope          TEXT NOT NULL DEFAULT 'personal' CHECK(scope IN ('business','personal')),
  mask           TEXT,
  balance        REAL NOT NULL DEFAULT 0,
  iso_currency   TEXT NOT NULL DEFAULT 'USD',
  plaid_account_id TEXT,
  archived       INTEGER NOT NULL DEFAULT 0,
  created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS categories (
  id    TEXT PRIMARY KEY,
  name  TEXT UNIQUE NOT NULL,
  kind  TEXT NOT NULL CHECK(kind IN ('expense','income')),
  icon  TEXT,
  tax_deductible INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS transactions (
  id               TEXT PRIMARY KEY,
  account_id       TEXT REFERENCES accounts(id) ON DELETE CASCADE,
  scope            TEXT NOT NULL CHECK(scope IN ('business','personal')),
  amount           REAL NOT NULL,              -- negative = outflow
  posted           TEXT NOT NULL,              -- YYYY-MM-DD
  name             TEXT NOT NULL,
  merchant         TEXT,
  category_id      TEXT REFERENCES categories(id),
  pending          INTEGER NOT NULL DEFAULT 0,
  recurring        INTEGER NOT NULL DEFAULT 0,
  note             TEXT DEFAULT '',
  split_scope      TEXT,                       -- set when user splits a shared tx
  split_amount     REAL,
  plaid_transaction_id TEXT UNIQUE,
  created_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tx_posted ON transactions(posted);
CREATE INDEX IF NOT EXISTS idx_tx_scope  ON transactions(scope);

CREATE TABLE IF NOT EXISTS budgets (
  id           TEXT PRIMARY KEY,
  category_id  TEXT REFERENCES categories(id),
  scope        TEXT NOT NULL CHECK(scope IN ('business','personal','all')),
  month_limit  REAL NOT NULL,
  period       TEXT NOT NULL DEFAULT 'monthly'
);

CREATE TABLE IF NOT EXISTS goals (
  id           TEXT PRIMARY KEY,
  name         TEXT NOT NULL,
  target       REAL NOT NULL,
  saved        REAL NOT NULL DEFAULT 0,
  monthly_plan REAL NOT NULL DEFAULT 0,
  target_date  TEXT,
  scope        TEXT NOT NULL DEFAULT 'personal' CHECK(scope IN ('business','personal')),
  account_id   TEXT REFERENCES accounts(id),
  completed_at TEXT,
  created_at   TEXT NOT NULL
);
"""


def init_db():
    c = _conn()
    c.executescript(SCHEMA)
    cols = {r[1] for r in c.execute("PRAGMA table_info(transactions)")}
    for name, definition in (("is_transfer", "INTEGER NOT NULL DEFAULT 0"), ("pending_transaction_id", "TEXT"), ("is_transfer_override", "INTEGER"), ("scope_override", "TEXT"), ("category_override", "INTEGER"), ("name_override", "INTEGER")):
        if name not in cols: c.execute(f"ALTER TABLE transactions ADD COLUMN {name} {definition}")
    seed_categories(c)
    c.commit()
    c.close()


def seed_categories(c):
    """Default taxonomy: business-flavored deductible cats + everyday personal."""
    rows = [
        ("cat-income",       "Income",            "income",  "\U0001F4B0", 0),
        ("cat-payroll",      "Payroll",           "income",  "\U0001F9B4", 0),
        ("cat-invoice",      "Invoice Payment",   "income",  "\U0001F9FE", 0),
        ("cat-refund",       "Refund / Reimbursement", "income", "\u21A9\uFE0F", 0),
        ("cat-groceries",    "Groceries",         "expense", "\U0001F6D2", 0),
        ("cat-dining",       "Dining & Coffee",   "expense", "\u2615", 0),
        ("cat-rent",         "Rent / Mortgage",   "expense", "\U0001F3E0", 0),
        ("cat-utilities",    "Utilities",         "expense", "\U0001F4A1", 0),
        ("cat-internet",     "Internet & Phone",  "expense", "\U0001F4F1", 0),
        ("cat-transport",    "Transport & Fuel",  "expense", "\u26FD", 0),
        ("cat-shopping",     "Shopping",          "expense", "\U0001F6CD", 0),
        ("cat-health",       "Health & Fitness",  "expense", "\U0001F4AA", 0),
        ("cat-insurance",    "Insurance",         "expense", "\U0001F6E1", 0),
        ("cat-personal-care", "Personal Care",    "expense", "\U0001F9FC", 0),
        ("cat-subscriptions","Subscriptions",     "expense", "\U0001F501", 0),
        ("cat-travel",       "Travel",            "expense", "\u2708\uFE0F", 0),
        ("cat-kids",         "Kids & Pets",       "expense", "\U0001F436", 0),
        ("cat-fun",          "Entertainment",     "expense", "\U0001F3AE", 0),
        ("cat-fees",         "Bank Fees & Interest", "expense", "\U0001F3E6", 0),
        # Business
        ("cat-biz-software", "Software & SaaS",   "expense", "\U0001FAB2", 1),
        ("cat-biz-ads",      "Advertising",       "expense", "\U0001F4E3", 1),
        ("cat-biz-contractors","Contractors",     "expense", "\U0001F465", 1),
        ("cat-biz-supplies", "Office Supplies",   "expense", "\U0001F5C2", 1),
        ("cat-biz-hardware", "Hardware & Equipment", "expense", "\U0001F5A5", 1),
        ("cat-biz-shipping", "Shipping & Postage","expense", "\U0001F4E6", 1),
        ("cat-biz-prof",     "Professional Services", "expense", "\u2696\uFE0F", 1),
        ("cat-biz-travel",   "Business Travel",   "expense", "\U0001FEB2", 1),
        ("cat-biz-meals",    "Business Meals",    "expense", "\U0001F37D", 1),
        ("cat-biz-fees",     "Payment Processing","expense", "\U0001F4B3", 1),
        ("cat-biz-rent",     "Studio / Coworking","expense", "\U0001F3D7", 1),
        ("cat-biz-other",    "Other Business",    "expense", "\U0001F4BC", 1),
    ]
    c.executemany(
        "INSERT OR IGNORE INTO categories(id,name,kind,icon,tax_deductible) VALUES(?,?,?,?,?)",
        rows,
    )


# ---------- query helpers ----------

def q(sql, args=()):
    c = _conn()
    try: return [dict(x) for x in c.execute(sql, args).fetchall()]
    finally: c.close()


def q1(sql, args=()):
    r = q(sql, args)
    return r[0] if r else None


def ex(sql, args=()):
    c = _conn()
    try:
        with c:
            cur = c.execute(sql, args)
            return cur.rowcount, cur.lastrowid
    finally: c.close()


def executemany(sql, seq):
    c = _conn()
    try:
        with c: c.executemany(sql, seq)
    finally: c.close()


def reset_all():
    """Wipe transactions/accounts/items/budgets/goals (keep config+categories)."""
    c = _conn()
    tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type=\'table\'")}
    for t in ("receipt_allocations", "receipt_jobs", "cancellation_events", "cancellation_jobs", "subscription_events", "subscription_matches", "subscription_learning", "subscriptions", "sync_state", "transactions", "budgets", "goals", "accounts", "items"):
        if t not in tables: continue
        c.execute(f"DELETE FROM {t}")
    c.commit()
    c.close()


def month_bounds(d=None):
    d = d or date.today()
    first = d.replace(day=1)
    if d.month == 12:
        nxt = d.replace(year=d.year + 1, month=1, day=1)
    else:
        nxt = d.replace(month=d.month + 1, day=1)
    return first.isoformat(), nxt.isoformat()
