"""Curated, read-only demonstration data. Never seed or inspect live finances."""
import calendar
import tempfile
import threading
from contextlib import contextmanager
from datetime import date, timedelta

import db
import subscriptions
import receipt_store

_lock = threading.RLock()
_storage = None
_seed_day = None

READ_PATHS = frozenset({
    '/config', '/accounts', '/items', '/categories', '/transactions',
    '/summary/overview', '/summary/networth', '/summary/cashflow',
    '/summary/categories', '/summary/heatmap', '/summary/matrix',
    '/reports/spending', '/budgets', '/subscriptions', '/goals',
    '/business/summary', '/monthly-plan', '/projections/defaults',
    '/export/transactions.csv', '/cancellations', '/cancellations/status',
    '/receipts', '/receipts/transaction', '/sync/status',
})


@contextmanager
def dataset():
    """Keep rollover and requests serialized; no process-global DB path changes."""
    global _storage, _seed_day
    with _lock:
        today = date.today()
        if _storage is None or _seed_day != today:
            candidate = tempfile.TemporaryDirectory(prefix='ledger-curated-demo-')
            try:
                with db.isolated_data(candidate.name):
                    seed(today)
            except Exception:
                candidate.cleanup()
                raise
            previous = _storage
            _storage, _seed_day = candidate, today
            if previous is not None:
                previous.cleanup()
        with db.isolated_data(_storage.name):
            yield


def seed(today):
    db.init_db()
    subscriptions.init_schema()
    receipt_store.init_schema()
    db.save_config({'owner_name': 'Alex', 'monthly_spending_target': 4200,
                    'tax_rate_business': .25, 'theme': 'light'})
    created = today.isoformat()
    accounts = [
        ('demo-checking', 'Everyday checking', 'depository', 'personal', 6840.25),
        ('demo-savings', 'Rainy day savings', 'depository', 'personal', 16200),
        ('demo-investing', 'Long-term investments', 'investment', 'personal', 28450),
        ('demo-studio', 'Juniper Studio checking', 'depository', 'business', 12860.50),
        ('demo-card', 'Studio rewards card', 'credit', 'business', -640.75),
    ]
    db.executemany('INSERT INTO accounts(id,name,type,scope,balance,created_at) VALUES(?,?,?,?,?,?)',
                   [(*row, created) for row in accounts])
    # Every name and amount below is invented. Dates roll with the calendar.
    recurring = [
        ('Maple Court rent', 'cat-rent', 1650, 1, 'personal', 'demo-checking'),
        ('Streamlight TV', 'cat-subscriptions', 17.99, 7, 'personal', 'demo-checking'),
        ('Soundwave Music', 'cat-subscriptions', 10.99, 14, 'personal', 'demo-checking'),
        ('Hearth Internet', 'cat-internet', 65, 10, 'personal', 'demo-checking'),
        ('Trailside Fitness', 'cat-health', 35, 18, 'personal', 'demo-checking'),
        ('Studio Design Suite', 'cat-biz-software', 49, 12, 'business', 'demo-card'),
        ('Cloudbox Storage', 'cat-biz-software', 12, 22, 'business', 'demo-card'),
        ('The Workshop desk', 'cat-biz-rent', 280, 3, 'business', 'demo-studio'),
    ]
    transactions = []

    def add(posted, account, scope, amount, merchant, category, recurring=False, transfer=False):
        if posted > today:
            return
        transactions.append((f'demo-tx-{len(transactions):04d}', account, scope, round(amount, 2),
                             posted.isoformat(), merchant, merchant, category,
                             int(recurring), int(transfer), '', created))

    for months_ago in range(11, -1, -1):
        index = today.year * 12 + today.month - 1 - months_ago
        year, month = index // 12, index % 12 + 1
        def day(n):
            return date(year, month, min(n, calendar.monthrange(year, month)[1]))
        for payday in (1, 15):
            add(day(payday), 'demo-checking', 'personal', 2750, 'Cedar Labs payroll', 'cat-payroll')
        for merchant, cat, amount, due, scope, account in recurring:
            add(day(due), account, scope, -amount, merchant, cat, True)
        add(day(5), 'demo-studio', 'business', 2400 + (11-months_ago)*60, 'Linden Design retainer', 'cat-invoice')
        add(day(19), 'demo-studio', 'business', 1250, 'Harbor House project', 'cat-invoice')
        for week in range(4):
            add(day(2 + week*7), 'demo-checking', 'personal', -(92.40 + week*8.15 + months_ago%3*5), 'Willow Market', 'cat-groceries')
            add(day(4 + week*7), 'demo-checking', 'personal', -(32.50 + week*6), 'Juniper Kitchen', 'cat-dining')
        add(day(3), 'demo-checking', 'personal', -46.80, 'City transit pass', 'cat-transport')
        add(day(6), 'demo-checking', 'personal', -84.50, 'Weekend Supply Co.', 'cat-shopping')
        add(day(11), 'demo-checking', 'personal', -42, 'Starlight Cinema', 'cat-fun')
        add(day(16), 'demo-studio', 'business', -350, 'Ellis Illustration', 'cat-biz-contractors')
        add(day(8), 'demo-card', 'business', -76.50, 'Paper & Pine supplies', 'cat-biz-supplies')
        add(day(20), 'demo-checking', 'personal', -500, 'Transfer to rainy day savings', 'cat-refund', transfer=True)
        add(day(20), 'demo-savings', 'personal', 500, 'Transfer from everyday checking', 'cat-refund', transfer=True)
    db.executemany('''INSERT INTO transactions
        (id,account_id,scope,amount,posted,name,merchant,category_id,recurring,is_transfer,note,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''', transactions)
    budgets = [('cat-groceries', 'personal', 550), ('cat-dining', 'personal', 220),
               ('cat-shopping', 'personal', 160), ('cat-fun', 'personal', 120),
               ('cat-transport', 'personal', 150), ('cat-subscriptions', 'personal', 45),
               ('cat-biz-software', 'business', 100), ('cat-biz-contractors', 'business', 700)]
    db.executemany('INSERT INTO budgets(id,category_id,scope,month_limit,period) VALUES(?,?,?,?,\'monthly\')',
                   [(f'demo-budget-{i}', *row) for i, row in enumerate(budgets)])
    goals = [('A softer landing', 20000, 16200, 500, 'personal', 'demo-savings', 240),
             ('A week in Kyoto', 6000, 2450, 300, 'personal', None, 390),
             ('Studio upgrade', 4000, 1800, 250, 'business', 'demo-studio', 300)]
    db.executemany('''INSERT INTO goals(id,name,target,saved,monthly_plan,scope,account_id,target_date,created_at)
        VALUES(?,?,?,?,?,?,?,?,?)''', [(f'demo-goal-{i}', *row[:6], (today+timedelta(days=row[6])).isoformat(), created)
                                      for i, row in enumerate(goals)])
    for i, (merchant, cat, amount, due, scope, account) in enumerate(recurring):
        due_date = date(today.year, today.month, min(due, calendar.monthrange(today.year, today.month)[1]))
        if due_date < today:
            index = today.year*12 + today.month
            year, month = index//12, index%12+1
            due_date = date(year, month, min(due, calendar.monthrange(year, month)[1]))
        sub = subscriptions.save({'merchant': merchant, 'amount': amount, 'cadence': 'monthly',
                                  'scope': scope, 'account_id': account, 'category_id': cat,
                                  'next_due': due_date.isoformat()})
        if merchant == 'Cloudbox Storage':
            db.ex("UPDATE subscriptions SET status='candidate',source='detected',confidence=.94 WHERE id=?", (sub['id'],))
        if merchant == 'Studio Design Suite':
            db.ex('UPDATE subscriptions SET observed_amount=54,price_review=1 WHERE id=?', (sub['id'],))
