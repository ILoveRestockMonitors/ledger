"""Local, suggestion-only category model trained on the owner's manual choices.

Nothing here writes to the database. A walk-forward test on real history measured
41-50% accuracy for merchants never seen before and about 85% overall at the
model's highest confidence, which is too low to apply automatically. So results only
reorder the category picker. No percentage is shown because this model's raw score
is overconfident.
"""
import math
import re
from collections import Counter, defaultdict

import category_picker
import db

_NOISE = {"debit", "card", "purchase", "pos", "from", "the", "inc", "llc", "com", "www", "on", "ca", "pay", "payment", "ach", "recurring"}
_MIN_EVIDENCE = 3
_MIN_SCORE = 0.6
_cache = {"key": None, "model": None}


def _features(tx):
    label = " ".join(str(tx.get("merchant") or tx.get("name") or "").lower().split())
    words = [w for w in re.findall(r"[a-z][a-z'&]{2,}", label) if w not in _NOISE]
    return set(words + ["b_" + a + "_" + b for a, b in zip(words, words[1:])])


def _train(rows):
    classes, seen, totals = Counter(), defaultdict(Counter), Counter()
    for row in rows:
        classes[row["category_id"]] += 1
        for feature in _features(row):
            seen[row["category_id"]][feature] += 1
            totals[feature] += 1
    return classes, seen, totals, len(rows)


def _model(conn):
    rows = [dict(r) for r in conn.execute("""SELECT t.id,t.name,t.merchant,t.category_id
        FROM transactions t JOIN categories c ON c.id=t.category_id AND c.kind='expense'
        LEFT JOIN accounts a ON a.id=t.account_id
        WHERE t.category_override=1 AND t.amount<0 AND COALESCE(t.is_transfer,0)=0 AND COALESCE(a.archived,0)=0
          AND lower(c.name) NOT IN ('uncategorized','uncategorised') ORDER BY t.posted,t.id""")]
    key = hash(tuple((r["id"], r["category_id"], r["merchant"]) for r in rows))
    if _cache["key"] != key:
        _cache.update(key=key, model=_train(rows))
    return _cache["model"]


def _rank(tx, model):
    classes, seen, totals, count = model
    features = [f for f in _features(tx) if totals[f]]
    if not count or not features or max(totals[f] for f in features) < _MIN_EVIDENCE:
        return []
    scores = {cid: math.log(n / count) + sum(math.log((seen[cid][f] + .05) / (n + .1)) for f in features) for cid, n in classes.items()}
    top = max(scores.values())
    total = sum(math.exp(s - top) for s in scores.values())
    return sorted(((math.exp(s - top) / total, cid) for cid, s in scores.items()), reverse=True)


def suggest(transaction_id, limit=3):
    """Return likely categories for one unassigned purchase, best first, without writing."""
    conn = db._conn()
    try:
        row = conn.execute("SELECT t.*, a.scope account_scope FROM transactions t LEFT JOIN accounts a ON a.id=t.account_id WHERE t.id=?", (transaction_id,)).fetchone()
        if not row:
            return []
        tx = dict(row)
        context = category_picker._context(conn)
        categories = context[0]
        if category_picker._protected(tx, categories, context[2]):
            return []
        if category_picker._AMBIGUOUS.search(str(tx.get("merchant") or "") + " " + str(tx.get("name") or "")):
            return []
        names = {c["id"]: c["name"] for c in categories}
        out = []
        direct = category_picker._choose(tx, conn, context)
        if direct:
            out.append(direct["category_id"])
        ranked = _rank(tx, _model(conn))
        if not out and (not ranked or ranked[0][0] < _MIN_SCORE):
            return []
        out += [cid for _, cid in ranked if cid not in out]
        return [{"category_id": cid, "category_name": names[cid]} for cid in out[:limit] if cid in names]
    finally:
        conn.close()
