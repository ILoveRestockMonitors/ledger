"""Readable merchant names from raw bank descriptions.

Plaid sometimes returns only the town as the merchant ("Capitola") when the
bank line says "DEBIT CARD PURCHASE AT CAPITOLA GROCER, CAPITOLA, CA ...".
We only replace Plaid's merchant when it is just the town from the bank line
and the bank line names a different store. Plaid's merchant is otherwise kept,
because its names are usually cleaner ("eBay", not "EBAY US").
"""
import re
from datetime import datetime

_PREFIX = re.compile(
    r"^\s*(?:debit card purchase|card transaction|debit card|pos purchase|pos debit|"
    r"recurring debit card|purchase authorized on \d\d/\d\d)\s*(?:at\b|:)?\s*", re.I)
# The store name ends at the first comma, a " - CODE" reference, or the date/card tail.
_END = re.compile(r",|\s+-\s+\S+|\s+on\s+\d{6}\b|\s+from\s+card#|\s{2,}", re.I)
_TOWN = re.compile(r",\s*([A-Za-z .'-]+?),\s*[A-Z]{2}\b")

_AMAZON_SUBSERVICES = (
    (re.compile(r"^\s*blink\b.*\b(?:amzn|amazon)\b", re.I), "Blink"),
    (re.compile(r"^\s*audible\b", re.I), "Audible"),
    (re.compile(r"^\s*(?:amazon\s+prime|amzn\s*prime|prime\s+video)\b", re.I), "Amazon Prime"),
    (re.compile(r"^\s*kindle\b", re.I), "Kindle"),
)


def _words(value):
    return re.findall(r"[a-z0-9&']+", str(value or "").casefold())


def _title(value):
    return " ".join(w[:1].upper() + w[1:].lower() for w in str(value).split())


def subservice_from_description(raw):
    text = str(raw or "")
    for pattern, label in _AMAZON_SUBSERVICES:
        if pattern.search(text):
            return label
    return None


def store_from_description(raw):
    """Return the store part of a card-purchase bank line, or None."""
    raw = str(raw or "")
    head = _PREFIX.match(raw)
    if not head:
        return None
    rest = raw[head.end():]
    store = _END.split(rest, 1)[0].strip(" :*#-")
    return store if len(_words(store)) >= 1 and len(store) >= 3 else None


def clean_merchant(raw, merchant):
    """Plaid's merchant, unless the bank line clearly holds a fuller store name."""
    sub = subservice_from_description(raw)
    if sub:
        return sub
    merchant = (merchant or "").strip()
    store = store_from_description(raw)
    if not store:
        return merchant or (raw or "")
    sw, mw = _words(store), _words(merchant)
    if not mw:
        return _title(store)
    town = _TOWN.search(str(raw))
    only_town = bool(town) and _words(town.group(1)) == mw and sw != mw
    return _title(store) if only_town else merchant


# Payment wrappers and bank words that are not part of the store's name.
_WRAPPERS = re.compile(
    r"^(?:aplpay|apple pay|applepay|gglpay|google pay|sq \*|sq\*|tst\*|tst \*|sp \*|sp\*|pp\*|"
    r"auth :|pos |purchase |pmusa \d+ )\s*", re.I)
_DROP = {"the", "inc", "llc", "co", "corp", "ltd", "usa", "us", "store", "of", "and", "&"}


_JUNK = re.compile(r"^(?:oth bank fee|bank fee|atm|withdrawal|deposit)\b", re.I)


def identity(tx):
    """The store's words without bank noise, or ''.

    "Grocery Outlet Of Sasanta Barbara" gives "grocery outlet sasanta barbara".
    Use ``same_store`` to compare two identities.
    """
    if tx.get("name_override"):
        label = tx.get("name")
    else:
        label = store_from_description(tx.get("name")) or tx.get("merchant") or tx.get("name")
    label = str(label or "").casefold()
    for _ in range(2):
        label = _WRAPPERS.sub("", label.strip())
    if _JUNK.search(label):
        return ""
    words = [w for w in re.findall(r"[a-z][a-z']+", label) if w not in _DROP]
    return " ".join(words) if words and len(" ".join(words)) >= 4 else ""


def same_store(a, b):
    """Equal, or one name continues the other (a town or branch added) with 2+ shared words."""
    if not a or not b:
        return False
    if a == b:
        return True
    short, long_ = sorted((a.split(), b.split()), key=len)
    return len(short) >= 2 and long_[:len(short)] == short


def alias_key(merchant):
    return " ".join(re.findall(r"[a-z0-9&']+", str(merchant or "").casefold()))


def init_schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS merchant_aliases(
        store_key TEXT PRIMARY KEY, display TEXT NOT NULL, updated_at TEXT NOT NULL)""")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(transactions)")}
    if "bank_merchant" not in cols:
        conn.execute("ALTER TABLE transactions ADD COLUMN bank_merchant TEXT")
    if "matched_name" not in cols:
        conn.execute("ALTER TABLE transactions ADD COLUMN matched_name TEXT")
    repair_submerchants(conn)



_GENERIC_AMAZON_RE = re.compile(
    r"^(?:amazon(?:\.com)?|amazon\s+marke?t?place(?:\s+n|\s+na(?:\s*-)?)?|amzn\s*mktp(?:\s+us)?|amazon\s+mktplace\s+pmts)$"
    r"|(?:amzn\.com/bill|amazon\s+mktpl\*|amazon\.com\*|amzn\s*mktp\*|amazon\s+mktplace\s+pmts|amazon\s+marketplace\s+namzn)",
    re.I,
)


def is_generic_amazon_descriptor(name):
    text = " ".join(str(name or "").split()).strip()
    return bool(text and _GENERIC_AMAZON_RE.search(text))


def repair_submerchants(conn):
    """Relabel generic Amazon merchant rows when bank text names a distinct subscription."""
    rows = conn.execute(
        """SELECT id, name, merchant FROM transactions
           WHERE COALESCE(name_override, 0) = 0
             AND lower(COALESCE(merchant, '')) = 'amazon'"""
    ).fetchall()
    for row in rows:
        sub = subservice_from_description(row["name"])
        if sub and row["merchant"] != sub:
            conn.execute(
                "UPDATE transactions SET bank_merchant=COALESCE(bank_merchant, merchant), merchant=? WHERE id=?",
                (sub, row["id"]),
            )
    # Historical bank/Rocket imports stamped name_override=1 onto raw Amazon bank descriptors
    # (e.g. 'Amazon Marketplace N', 'AMAZON MKTPL*... Amzn.com/bill WA USA 6104'). Clear
    # name_override only on those raw descriptors while keeping custom user names intact.
    ov_rows = conn.execute(
        "SELECT id, name, merchant FROM transactions WHERE amount < 0 AND COALESCE(name_override, 0) = 1 "
        "AND (lower(name) LIKE '%amazon%' OR lower(name) LIKE '%amzn%' OR lower(COALESCE(merchant, '')) = 'amazon')"
    ).fetchall()
    for orow in ov_rows:
        rid, rname, rmerch = orow[0], orow[1], orow[2]
        if str(rname or "").strip().lower() == "blink":
            if rmerch != "Blink":
                conn.execute("UPDATE transactions SET merchant='Blink' WHERE id=?", (rid,))
        elif is_generic_amazon_descriptor(rname):
            conn.execute("UPDATE transactions SET name_override=0, merchant='Amazon' WHERE id=?", (rid,))


def aliases(conn):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='merchant_aliases'").fetchone():
        return {}
    return {r[0]: r[1] for r in conn.execute("SELECT store_key, display FROM merchant_aliases")}


def bank_merchant(raw, plaid_merchant):
    """The bank's store name before any owner-taught name."""
    return clean_merchant(raw, plaid_merchant)


def display_merchant(raw, plaid_merchant, alias_map):
    base = clean_merchant(raw, plaid_merchant)
    return alias_map.get(alias_key(base), base)


def remember(conn, transaction_id, display):
    """Use ``display`` for every bank purchase with this row's bank store name.

    Changes only the merchant column (and this row's own renamed name), never
    amounts, dates or categories. Returns the number of purchases renamed.
    """
    display = " ".join(str(display or "").split())
    if not display or len(display) > 200:
        raise ValueError("Enter a store name of 200 characters or less.")
    init_schema(conn)
    row = conn.execute("SELECT * FROM transactions WHERE id=?", (transaction_id,)).fetchone()
    if not row or not row["account_id"]:
        raise ValueError("Only bank purchases can teach a store name.")
    key = alias_key(row["bank_merchant"] or row["merchant"] or row["name"])
    if not key:
        raise ValueError("This purchase has no bank store name to remember.")
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute("""INSERT INTO merchant_aliases VALUES(?,?,?) ON CONFLICT(store_key)
        DO UPDATE SET display=excluded.display, updated_at=excluded.updated_at""", (key, display, now))
    ids = [r[0] for r in conn.execute("""SELECT id, COALESCE(bank_merchant, merchant, name) FROM transactions
        WHERE account_id IS NOT NULL""") if alias_key(r[1]) == key]
    for tid in ids:
        conn.execute("""UPDATE transactions SET bank_merchant=COALESCE(bank_merchant, merchant), merchant=?,
            name=CASE WHEN COALESCE(name_override,0)=1 AND id=? THEN ? ELSE name END WHERE id=?""",
            (display, transaction_id, display, tid))
    return len(ids)
