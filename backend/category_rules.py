"""Explicit same-name category rules and reviewed, reversible bulk edits."""
import hashlib
import json
import secrets
import time
import unicodedata
from datetime import datetime

import db


def name_key(tx):
    label = tx.get('name') if tx.get('name_override') else tx.get('merchant') or tx.get('name')
    return ' '.join(unicodedata.normalize('NFKC', str(label or '')).split()).casefold()


def init_schema(conn=None):
    own = conn is None
    c = conn or db._conn()
    try:
        for sql in (
            '''CREATE TABLE IF NOT EXISTS transaction_category_rules(
                name_key TEXT NOT NULL, scope TEXT NOT NULL, category_id TEXT NOT NULL REFERENCES categories(id),
                label TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(name_key,scope))''',
            '''CREATE TABLE IF NOT EXISTS category_edit_previews(
                id TEXT PRIMARY KEY, payload TEXT NOT NULL, expires_at REAL NOT NULL)''',
            '''CREATE TABLE IF NOT EXISTS category_edit_batches(
                id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL, undone_at TEXT)''',
        ): c.execute(sql)
        if own: c.commit()
    finally:
        if own: c.close()


def match(tx, conn=None):
    if tx.get('category_override') or tx.get('is_transfer') or float(tx.get('amount') or 0) >= 0:
        return None
    own = conn is None
    c = conn or db._conn()
    try:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='transaction_category_rules'").fetchone():
            return None
        row = c.execute('''SELECT r.category_id FROM transaction_category_rules r
            JOIN categories cat ON cat.id=r.category_id AND cat.kind='expense'
            WHERE r.name_key=? AND r.scope=?''', (name_key(tx), tx.get('scope'))).fetchone()
        return {'category_id': row['category_id'], 'reason': 'Your saved rule for this purchase name', 'source': 'rule', 'confidence': 1} if row else None
    finally:
        if own: c.close()


def _rows(c):
    return [dict(r) for r in c.execute('''SELECT t.*,COALESCE(a.name,'Cash / manual') account_name,a.mask account_mask,
        COALESCE(a.archived,0) archived,cat.name category_name,
        EXISTS(SELECT 1 FROM receipt_allocations ra WHERE ra.transaction_id=t.id AND ra.active=1) has_split
        FROM transactions t LEFT JOIN accounts a ON a.id=t.account_id
        LEFT JOIN categories cat ON cat.id=t.category_id''')]


def _fingerprint(row):
    return hashlib.sha256(json.dumps({k:row.get(k) for k in (
        'id','name','merchant','name_override','account_id','scope','category_id','category_override',
        'posted','amount','pending','is_transfer','has_split','archived')},sort_keys=True).encode()).hexdigest()


def preview(transaction_id, category_id):
    import receipt_store
    receipt_store.init_schema()
    init_schema()
    c = db._conn()
    try:
        all_rows = _rows(c)
        anchor = next((r for r in all_rows if r['id']==transaction_id),None)
        if not anchor: raise ValueError('Transaction not found.')
        cat=c.execute("SELECT id,name FROM categories WHERE id=? AND kind='expense'",(category_id,)).fetchone()
        if not cat: raise ValueError('Choose a spending category.')
        if anchor['amount']>=0 or anchor['is_transfer'] or anchor['archived']:
            raise ValueError('Same-name category changes are available for purchases in active accounts.')
        key=name_key(anchor)
        if not key: raise ValueError('This purchase needs a name first.')
        candidates=[r for r in all_rows if r['id']!=anchor['id'] and not r['archived']
            and r['scope']==anchor['scope'] and r['amount']<0 and not r['is_transfer'] and name_key(r)==key
            and r['category_id']!=category_id]
        skipped=sum(bool(r['has_split']) for r in candidates)
        candidates=[r for r in candidates if not r['has_split']]
        candidates.sort(key=lambda r:(r['posted'],r['id']),reverse=True)
        token=secrets.token_hex(24)
        label=anchor['name'] if anchor.get('name_override') else anchor['merchant'] or anchor['name']
        payload={'anchor_id':anchor['id'],'anchor_fingerprint':_fingerprint(anchor),'name_key':key,
            'label':label,'scope':anchor['scope'],'category_id':category_id,'category_name':cat['name'],
            'rows':[{'id':r['id'],'fingerprint':_fingerprint(r)} for r in candidates]}
        c.execute('DELETE FROM category_edit_previews WHERE expires_at<?',(time.time(),))
        c.execute('INSERT INTO category_edit_previews VALUES(?,?,?)',(token,json.dumps(payload),time.time()+900))
        c.commit()
        return {k:payload[k] for k in ('label','scope','category_id','category_name')} | {
            'preview_id':token,'count':len(candidates),'skipped_splits':skipped,
            'transactions':[{k:r.get(k) for k in ('id','posted','name','merchant','name_override','amount','pending','account_name','account_mask','category_name','category_override')} for r in candidates]}
    finally:c.close()


def apply(preview_id, remember=False):
    if type(remember) is not bool: raise ValueError('Choose whether to remember this category.')
    init_schema()
    c=db._conn()
    try:
        c.execute('BEGIN IMMEDIATE')
        saved=c.execute('SELECT * FROM category_edit_previews WHERE id=?',(preview_id,)).fetchone()
        if not saved or saved['expires_at']<time.time():raise ValueError('This preview expired. Reopen the purchase to review it again.')
        p=json.loads(saved['payload']);rows={r['id']:r for r in _rows(c)}
        anchor=rows.get(p['anchor_id'])
        if not anchor or _fingerprint(anchor)!=p['anchor_fingerprint']:
            raise ValueError('The original purchase changed. Reopen it to review a fresh preview.')
        old=[]
        for item in p['rows']:
            row=rows.get(item['id'])
            if not row or _fingerprint(row)!=item['fingerprint']:
                raise ValueError('A purchase in this preview changed. Reopen the original purchase to review a fresh preview.')
            old.append({k:row[k] for k in ('id','category_id','category_override')})
        rule_before=c.execute('SELECT * FROM transaction_category_rules WHERE name_key=? AND scope=?',(p['name_key'],p['scope'])).fetchone()
        now=datetime.now().isoformat(timespec='microseconds')
        for row in old:
            c.execute('UPDATE transactions SET category_id=?,category_override=1 WHERE id=?',(p['category_id'],row['id']))
        if remember:
            c.execute('''INSERT INTO transaction_category_rules VALUES(?,?,?,?,?)
                ON CONFLICT(name_key,scope) DO UPDATE SET category_id=excluded.category_id,label=excluded.label,updated_at=excluded.updated_at''',
                (p['name_key'],p['scope'],p['category_id'],p['label'],now))
        batch=secrets.token_hex(16)
        audit={'category_id':p['category_id'],'before':old,'rule_before':dict(rule_before) if rule_before else None,
            'rule_changed':remember,'name_key':p['name_key'],'scope':p['scope'],'rule_updated_at':now}
        c.execute('INSERT INTO category_edit_batches(id,payload,created_at) VALUES(?,?,?)',(batch,json.dumps(audit),now))
        c.execute('DELETE FROM category_edit_previews WHERE id=?',(preview_id,))
        c.commit()
        return {'ok':True,'changed':len(old),'remembered':remember,'batch_id':batch}
    finally:c.close()


def undo(batch_id):
    init_schema();c=db._conn()
    try:
        c.execute('BEGIN IMMEDIATE')
        batch=c.execute('SELECT * FROM category_edit_batches WHERE id=?',(batch_id,)).fetchone()
        if not batch or batch['undone_at']:raise ValueError('This category change has already been undone or is unavailable.')
        p=json.loads(batch['payload']);restored=0;skipped=0
        for old in p['before']:
            current=c.execute('SELECT category_id,category_override FROM transactions WHERE id=?',(old['id'],)).fetchone()
            split=c.execute('SELECT 1 FROM receipt_allocations WHERE transaction_id=? AND active=1',(old['id'],)).fetchone()
            if not current or split or current['category_id']!=p['category_id'] or current['category_override']!=1:
                skipped+=1;continue
            c.execute('UPDATE transactions SET category_id=?,category_override=? WHERE id=?',(old['category_id'],old['category_override'],old['id']));restored+=1
        if p['rule_changed']:
            current=c.execute('SELECT updated_at FROM transaction_category_rules WHERE name_key=? AND scope=?',(p['name_key'],p['scope'])).fetchone()
            if current and current['updated_at']==p['rule_updated_at']:
                old=p['rule_before']
                if old:c.execute('UPDATE transaction_category_rules SET category_id=?,label=?,updated_at=? WHERE name_key=? AND scope=?',(old['category_id'],old['label'],old['updated_at'],old['name_key'],old['scope']))
                else:c.execute('DELETE FROM transaction_category_rules WHERE name_key=? AND scope=?',(p['name_key'],p['scope']))
        c.execute('UPDATE category_edit_batches SET undone_at=? WHERE id=?',(datetime.now().isoformat(),batch_id));c.commit()
        return {'ok':True,'restored':restored,'skipped':skipped}
    finally:c.close()
