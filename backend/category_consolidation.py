"""Consolidate equivalent imported category names without changing financial totals.

Canonical IDs stay compatible with provider category mappings. Run on startup so
re-imported aliases are folded back into the same category on the next start.
Broad categories (Health & Fitness, Transport & Fuel) deliberately remain distinct.
"""
import json
import unicodedata
from decimal import Decimal, ROUND_HALF_UP


def name_key(name):
    return ' '.join(unicodedata.normalize('NFKC', name).split()).casefold()


# Only explicit equivalents; never infer that a broad category equals a subtype.
GROUPS = (
    ('cat-shopping', 'Shopping', ('shopping', 'shopping (other)')),
    ('cat-dining', 'Eat out', ('dining & coffee', 'eat out')),
    ('cat-utilities', 'Bills & Utilities', ('utilities', 'bills & utilities')),
    ('cat-travel', 'Travel & Vacation', ('travel', 'travel & vacation')),
    (None, 'Healthcare', ('healthcare', 'medical')),
)


def _quote(identifier):
    return '"' + identifier.replace('"', '""') + '"'


def _replace(value, aliases):
    if isinstance(value, str):
        return aliases.get(value, value)
    if isinstance(value, list):
        return [_replace(item, aliases) for item in value]
    if isinstance(value, dict):
        return {key: _replace(item, aliases) for key, item in value.items()}
    return value


def consolidate(conn):
    """Run within the caller's transaction; return the IDs merged this time.

    References in receipt/undo snapshots follow the retained ID too. Budget
    envelopes combine only within the same scope and period, preserving limits.
    """
    rows = [dict(row) for row in conn.execute('SELECT * FROM categories ORDER BY id')]
    aliases = {}
    # Case/spacing variants count as duplicates only with matching semantics.
    groups = {}
    for row in rows:
        groups.setdefault((name_key(row['name']), row['kind'], row['tax_deductible']), []).append(row)
    for group in groups.values():
        if len(group) > 1:
            target = next((r for r in group if r['id'].startswith('cat-')), group[0])
            aliases.update({r['id']: target['id'] for r in group if r['id'] != target['id']})
    renames = {}
    for preferred, label, names in GROUPS:
        group = [r for r in rows if name_key(r['name']) in names and r['kind'] == 'expense' and not r['tax_deductible']]
        if len(group) < 2:
            continue
        target = next((r for r in group if r['id'] == preferred), None)
        target = target or next((r for r in group if name_key(r['name']) == name_key(label)), group[0])
        # Explicit group choice supersedes a normalized-name choice.
        aliases.pop(target['id'], None)
        aliases.update({r['id']: target['id'] for r in group if r['id'] != target['id']})
        renames[target['id']] = label
    for old in aliases:
        target = aliases[old]
        while target in aliases:
            target = aliases[target]
        aliases[old] = target
    if not aliases:
        return {}

    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    for table in tables:
        if table == 'categories':
            continue
        columns = {r[1] for r in conn.execute('PRAGMA table_info(' + _quote(table) + ')')}
        # Include audit and original-category columns even where no FK is declared.
        refs = {col for col in columns if col == 'category_id' or col.endswith('_category_id')}
        refs.update(r[3] for r in conn.execute('PRAGMA foreign_key_list(' + _quote(table) + ')') if r[2] == 'categories')
        for col in refs:
            for old, target in aliases.items():
                conn.execute(f'UPDATE {_quote(table)} SET {_quote(col)}=? WHERE {_quote(col)}=?', (target, old))
        # Receipt proposals and reversible category-edit batches embed category IDs.
        for col in columns & {'payload', 'proposal'}:
            for row in conn.execute(f'SELECT rowid,{_quote(col)} FROM {_quote(table)} WHERE {_quote(col)} IS NOT NULL').fetchall():
                try:
                    value = json.loads(row[1])
                except (ValueError, TypeError):
                    continue
                replacement = _replace(value, aliases)
                if replacement != value:
                    conn.execute(f'UPDATE {_quote(table)} SET {_quote(col)}=? WHERE rowid=?', (json.dumps(replacement), row[0]))

    for target in set(aliases.values()):
        budgets = conn.execute('SELECT * FROM budgets WHERE category_id=? ORDER BY id', (target,)).fetchall()
        envelopes = {}
        for budget in budgets:
            envelopes.setdefault((budget['scope'], budget['period']), []).append(budget)
        for group in envelopes.values():
            if len(group) < 2:
                continue
            total = sum(Decimal(str(b['month_limit'])) for b in group).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
            conn.execute('UPDATE budgets SET month_limit=? WHERE id=?', (float(total), group[0]['id']))
            conn.executemany('DELETE FROM budgets WHERE id=?', [(b['id'],) for b in group[1:]])
    conn.executemany('DELETE FROM categories WHERE id=?', [(old,) for old in aliases])
    for target, label in renames.items():
        conn.execute('UPDATE categories SET name=? WHERE id=?', (label, target))
    return aliases
