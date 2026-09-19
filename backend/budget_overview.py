"""Complete monthly purchase totals, including categories without envelopes."""
from datetime import date
import re

import db
import receipt_store
from reports import _cents, _money


def month_bounds(month=None, as_of=None):
    today = as_of or date.today()
    month = month or today.strftime('%Y-%m')
    if not isinstance(month, str) or not re.fullmatch(r'\d{4}-\d{2}', month):
        raise ValueError('month must be YYYY-MM')
    try:
        start = date.fromisoformat(month + '-01')
    except ValueError:
        raise ValueError('month must be a valid calendar month')
    if start.year < 1900 or start > today:
        raise ValueError('Choose a month between January 1900 and this month')
    end = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    return start.isoformat(), end.isoformat()


def overview(month=None, scope=None, as_of=None):
    today = as_of or date.today()
    start, end = month_bounds(month, today)
    month = start[:7]
    if scope not in (None, 'personal', 'business'):
        raise ValueError('scope must be personal or business')
    rows = db.q('''SELECT t.id,t.name,t.posted,t.amount,t.pending,t.scope,t.category_id,
                  a.name account_name,a.mask account_mask,c.name category_name
                  FROM transactions t LEFT JOIN accounts a ON a.id=t.account_id
                  LEFT JOIN categories c ON c.id=t.category_id
                  WHERE t.amount<0 AND COALESCE(t.is_transfer,0)=0
                  AND t.posted>=? AND t.posted<? AND t.posted<=?'''
                + (' AND t.scope=?' if scope else '') + ' ORDER BY t.posted DESC,t.id',
                (start[:4]+'-01-01', str(int(start[:4])+1)+'-01-01', today.isoformat(), *((scope,) if scope else ())))
    history = {f'{start[:4]}-{i:02}': {'month': f'{start[:4]}-{i:02}', 'posted_cents': 0, 'pending_cents': 0}
               for i in range(1, 13)}
    selected = []
    for row in rows:
        field = 'pending_cents' if row['pending'] else 'posted_cents'
        history[row['posted'][:7]][field] += -_cents(row['amount'])
        if start <= row['posted'] < end:
            selected.append(row)
    amap = receipt_store.allocation_map([t['id'] for t in selected])
    categories = {r['id']: r for r in db.q('SELECT id,name,icon FROM categories')}
    groups, uncategorized = {}, []
    for tx in selected:
        parts = amap.get(tx['id']) or [{'amount_cents': -_cents(tx['amount']), 'category_id': tx['category_id']}]
        missing = 0
        for part in parts:
            cat = categories.get(part.get('category_id'))
            is_missing = not cat or not cat['name'].strip() or cat['name'].strip().casefold() in ('uncategorized', 'uncategorised')
            key = None if is_missing else cat['id']
            group = groups.setdefault(key, {'id': key, 'name': 'Uncategorized' if is_missing else cat['name'],
                'icon': '○' if is_missing else cat['icon'], 'posted_cents': 0, 'pending_cents': 0})
            group['pending_cents' if tx['pending'] else 'posted_cents'] += part['amount_cents']
            if is_missing:
                missing += part['amount_cents']
        if missing:
            uncategorized.append({**tx, 'uncategorized_amount': _money(missing), 'purchase_amount': -tx['amount'],
                                  'partially_categorized': missing != -_cents(tx['amount'])})
    summary = history[month]
    total_cents = summary['posted_cents'] + summary['pending_cents']
    missing = groups.get(None, {'posted_cents': 0, 'pending_cents': 0})
    missing_cents = missing['posted_cents'] + missing['pending_cents']
    assert sum(g['posted_cents']+g['pending_cents'] for g in groups.values()) == total_cents
    def monetary(row):
        return {**{k:v for k,v in row.items() if not k.endswith('_cents')},
            'posted': _money(row['posted_cents']), 'pending': _money(row['pending_cents']),
            'total': _money(row['posted_cents']+row['pending_cents'])}
    # Refunds/credits in an expense category are shown separately. Gross
    # purchases remain comparable with Ledger's existing spending reports.
    credits = db.q('''SELECT t.amount FROM transactions t LEFT JOIN categories c ON c.id=t.category_id
        WHERE t.amount>0 AND COALESCE(t.is_transfer,0)=0 AND COALESCE(t.pending,0)=0
        AND t.posted>=? AND t.posted<? AND t.posted<=? AND (c.kind='expense' OR t.category_id='cat-refund')'''
        + (' AND t.scope=?' if scope else ''), (start,end,today.isoformat(),*((scope,) if scope else ())))
    return {'month': month, 'scope': scope, 'as_of': today.isoformat(), 'summary': {
        **monetary(summary), 'categorized': _money(total_cents-missing_cents),
        'uncategorized': _money(missing_cents), 'transaction_count': len(selected),
        'uncategorized_count': len(uncategorized), 'refunds': _money(sum(_cents(r['amount']) for r in credits))},
        'categories': sorted(map(monetary, groups.values()), key=lambda r:(-r['total'],r['name'])),
        'uncategorized_transactions': uncategorized,
        'months': [{**monetary(r), 'future': r['month'] > today.strftime('%Y-%m')} for r in history.values()]}
