"""Generate a realistic 9-month demo dataset: 1 business checking, 1 business
credit card, 2 personal accounts. Deterministic-ish via random.seed so numbers
are reproducible.
"""
import random
import sqlite3
import uuid
from datetime import date, timedelta

import db

NOW = date.today()


def _d(days_ago):
    return (NOW - timedelta(days=days_ago)).isoformat()


def seed_demo(force=False):
    existing = db.q1("SELECT COUNT(*) n FROM accounts WHERE item_id LIKE 'demo%'")
    if existing and existing["n"] > 0 and not force:
        return {"ok": True, "already": True}
    if force:
        db.reset_all()

    rnd = random.Random(42)
    now = db.q1("SELECT datetime('now') ts")["ts"]

    # ---- items ----
    items = [
        ("demo-item-bizbank", "First Biz Bank", "business"),
        ("demo-item-personal", "Everyday Credit Union", "personal"),
    ]
    for iid, inst, sc in items:
        db.ex("INSERT INTO items(id,institution,env,created_at) VALUES(?,?,?,?)",
              (iid, inst, "demo", now))

    accounts = [
        dict(id="demo-acct-biz-check", item_id="demo-item-bizbank", name="Business Checking",
             official_name="First Biz Bank Business Checking ••4821", type="depository",
             subtype="checking", scope="business", mask="4821", balance=24318.55),
        dict(id="demo-acct-biz-card", item_id="demo-item-bizbank", name="Biz Rewards Card",
             official_name="First Biz Bank Business Card ••9034", type="credit",
             subtype="credit card", scope="business", mask="9034", balance=-1842.20),
        dict(id="demo-acct-per-check", item_id="demo-item-personal", name="Everyday Checking",
             official_name="Everyday CU Free Checking ••1177", type="depository",
             subtype="checking", scope="personal", mask="1177", balance=8215.10),
        dict(id="demo-acct-per-save", item_id="demo-item-personal", name="Rainy Day Savings",
             official_name="Everyday CU High-Yield Savings ••2290", type="depository",
             subtype="savings", scope="personal", mask="2290", balance=15240.00),
    ]
    for a in accounts:
        a["iso_currency"] = "USD"
        a["plaid_account_id"] = None
        a["archived"] = 0
        a["created_at"] = now
    db.executemany(
        """INSERT INTO accounts(id,item_id,name,official_name,type,subtype,scope,mask,balance,
                                iso_currency,plaid_account_id,archived,created_at)
           VALUES(:id,:item_id,:name,:official_name,:type,:subtype,:scope,:mask,:balance,
                  :iso_currency,:plaid_account_id,:archived,:created_at)""",
        accounts,
    )

    tx_rows = []

    def add(acct, scope, amount, days_ago, name, merchant, cat, recurring=0, note=""):
        tx_rows.append((
            f"dtx-{uuid.uuid4().hex[:14]}", acct, scope, round(amount, 2),
            _d(days_ago), name, merchant, cat, 0, recurring, note, None, f"pl-{uuid.uuid4().hex[:14]}", now,
        ))

    # ---- recurring business income: 3 clients, monthly invoices ----
    for m in range(9):
        base_day = NOW - timedelta(days=30 * m)
        add("demo-acct-biz-check", "business", rnd.uniform(4200, 5200), max(0, (NOW - base_day.replace(day=5)).days) + rnd.randint(0, 2),
            f"ACME Studio invoice #{1000+m}", "ACME Studio LLC", "cat-invoice", 1)
        add("demo-acct-biz-check", "business", rnd.uniform(1500, 2400), max(0, (NOW - base_day.replace(day=12)).days) + rnd.randint(0, 2),
            f"Northwind retainer {NOW.year}-{m}", "Northwind Traders", "cat-invoice", 1)
        if m % 2 == 0:
            add("demo-acct-biz-check", "business", rnd.uniform(600, 1800), rnd.randint(0, 30 * m),
                "Hooli project milestone", "Hooli", "cat-income")

    # ---- recurring business expenses ----
    biz_monthly = [
        ("Adobe Creative Cloud", "Adobe", "cat-biz-software", 54.99),
        ("Figma Organization", "Figma", "cat-biz-software", 45.00),
        ("Google Workspace", "Google", "cat-biz-software", 18.00),
        ("Meta Ads campaign", "Meta Ads", "cat-biz-ads", 320.00),
        ("Coworking desk rent", "WeWork", "cat-biz-rent", 450.00),
        ("Stripe processing fees", "Stripe", "cat-biz-fees", 88.00),
    ]
    for m in range(9):
        day_anchor = NOW - timedelta(days=30 * m)
        for name, merch, cat, amt in biz_monthly:
            jitter = amt * rnd.uniform(0.92, 1.08)
            dd = max(0, (NOW - day_anchor).days - rnd.randint(1, 6))
            add("demo-acct-biz-card", "business", -jitter, dd, name, merch, cat, 1)
        # occasional contractors / supplies / travel
        if rnd.random() < 0.8:
            add("demo-acct-biz-check", "business", -rnd.uniform(300, 1400), rnd.randint(0, 30 * m + 5),
                "Contractor payout", "Upwork", "cat-biz-contractors")
        if rnd.random() < 0.5:
            add("demo-acct-biz-card", "business", -rnd.uniform(40, 260), rnd.randint(0, 30 * m + 5),
                rnd.choice(["Office supplies order", "Amazon Business", "Staples"]),
                rnd.choice(["Amazon", "Staples"]), "cat-biz-supplies")
        if rnd.random() < 0.35:
            add("demo-acct-biz-card", "business", -rnd.uniform(220, 900), rnd.randint(0, 30 * m + 5),
                rnd.choice(["Delta Air Lines", "Hotel block", "Uber business"]),
                rnd.choice(["Delta", "Marriott", "Uber"]), "cat-biz-travel")

    # ---- recurring personal ----
    per_monthly = [
        ("Netflix", "Netflix", "cat-subscriptions", 15.49),
        ("Spotify Premium", "Spotify", "cat-subscriptions", 11.99),
        ("Comcast Xfinity Internet", "Xfinity", "cat-internet", 79.99),
        ("Verizon Wireless", "Verizon", "cat-internet", 68.50),
        ("State Farm Auto Insurance", "State Farm", "cat-insurance", 132.00),
        ("Planet Fitness", "Planet Fitness", "cat-health", 24.99),
        ("Rent payment — Maple Court Apts", "Maple Court", "cat-rent", 1650.00),
    ]
    for m in range(9):
        anchor = NOW - timedelta(days=30 * m)
        for name, merch, cat, amt in per_monthly:
            jitter = amt * rnd.uniform(0.98, 1.02)
            dd = max(0, (NOW - anchor).days - rnd.randint(1, 8))
            add("demo-acct-per-check", "personal", -jitter, dd, name, merch, cat, 1)
        # groceries weekly-ish
        for w in range(4):
            add("demo-acct-per-check", "personal", -rnd.uniform(65, 190), max(0, 30*m + w*7 - rnd.randint(0, 3)),
                rnd.choice(["Whole Foods Market", "Trader Joe's", "Kroger"]),
                rnd.choice(["Whole Foods", "Trader Joe's", "Kroger"]), "cat-groceries")
        # dining & fun
        for _ in range(rnd.randint(4, 9)):
            add("demo-acct-per-check", "personal", -rnd.uniform(8, 64), rnd.randint(0, max(1, 30*m+4)),
                rnd.choice(["Starbucks", "Chipotle", "Local Taqueria", "AMC Theatres", "Steam"]),
                rnd.choice(["Starbucks", "Chipotle", "Doordash", "AMC", "Steam"]),
                rnd.choice(["cat-dining", "cat-fun"]))
        if rnd.random() < 0.7:
            add("demo-acct-per-check", "personal", -rnd.uniform(35, 95), rnd.randint(0, 30*m+4),
                rnd.choice(["Shell", "Chevron", "Lyft"]), rnd.choice(["Shell", "Chevron", "Lyft"]), "cat-transport")
        if rnd.random() < 0.4:
            add("demo-acct-per-check", "personal", -rnd.uniform(20, 120), rnd.randint(0, 30*m+4),
                rnd.choice(["Target run", "Costco", "CVS pharmacy"]), rnd.choice(["Target", "Costco", "CVS"]), "cat-shopping")
        if rnd.random() < 0.3:
            add("demo-acct-per-save", "personal", rnd.uniform(200, 800), rnd.randint(0, 28),
                "Transfer to savings", "Internal Transfer", "cat-refund")

    # salary-like personal income every month (side payouts)
    for m in range(9):
        add("demo-acct-per-check", "personal", rnd.uniform(3100, 3400), max(0, 30*m - rnd.randint(0, 3)),
            "Payroll deposit", "Employer Inc Payroll", "cat-payroll", 1)

    db.executemany(
        """INSERT INTO transactions(id,account_id,scope,amount,posted,name,merchant,category_id,
                                    pending,recurring,note,split_scope,plaid_transaction_id,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        tx_rows,
    )

    # ---- budgets ----
    budgets = [
        ("bud-groc", "cat-groceries", "personal", 550),
        ("bud-dine", "cat-dining", "personal", 220),
        ("bud-shop", "cat-shopping", "personal", 180),
        ("bud-fun", "cat-fun", "personal", 150),
        ("bud-subs", "cat-subscriptions", "personal", 60),
        ("bud-transp", "cat-transport", "personal", 160),
        ("bud-bizads", "cat-biz-ads", "business", 400),
        ("bud-bizsoft", "cat-biz-software", "business", 150),
        ("bud-bizcontr", "cat-biz-contractors", "business", 1200),
    ]
    for bid, cid, sc, lim in budgets:
        db.ex("INSERT INTO budgets(id,category_id,scope,month_limit,period) VALUES(?,?,?,?,?)",
              (bid, cid, sc, lim, "monthly"))

    # ---- goals ----
    goals = [
        ("goal-emergency", "Emergency fund (6mo)", 18000, 15240, 500, (date(NOW.year+1, 6, 1)).isoformat(), "personal", "demo-acct-per-save"),
        ("goal-macbook", "New MacBook Pro", 3200, 1150, 250, (date(NOW.year+1, 2, 1)).isoformat(), "business", "demo-acct-biz-check"),
        ("goal-japan", "Japan trip", 6500, 2100, 350, (date(NOW.year+2, 4, 1)).isoformat(), "personal", None),
    ]
    for gid, name, target, saved, plan, tdate, sc, acct in goals:
        db.ex("""INSERT INTO goals(id,name,target,saved,monthly_plan,target_date,scope,account_id,completed_at,created_at)
                 VALUES(?,?,?,?,?,?,?,?,NULL,?)""", (gid, name, target, saved, plan, tdate, sc, acct, now))

    n = len(tx_rows)
    return {"ok": True, "already": False, "transactions": n, "accounts": len(accounts)}
