"""Analytics: summaries, budgets, recurring detection, reports.

Measured totals come from SQLite; historical net worth is reconstructed, not a balance snapshot.
"""
import calendar
from collections import defaultdict
from datetime import date, datetime, timedelta

from db import q, q1, month_bounds
import receipt_store


def month_list(n):
    """Last n months as (year, month) tuples ending this month."""
    out = []
    d = date.today()
    y, m = d.year, d.month
    for _ in range(n):
        out.append((y, m))
        m -= 1
        if m == 0:
            y -= 1
            m = 12
    return list(reversed(out))


def mbounds(y, m):
    return date(y, m, 1).isoformat(), date(y + (m == 12), (m % 12) + 1, 1).isoformat()


def _flows(where="1=1", args=()):
    row = q1(
        f"""SELECT
             COALESCE(SUM(CASE WHEN amount>0 THEN amount ELSE 0 END),0) AS income,
             COALESCE(SUM(CASE WHEN amount<0 THEN -amount ELSE 0 END),0) AS spend
           FROM transactions WHERE pending=0 AND is_transfer=0 AND posted<=date('now','localtime') AND {where}""",
        args,
    )
    return row


# ---------------- overview ----------------

def overview(scope=None):
    """scope None => combined; else 'business' or 'personal'."""
    sc = "AND scope=?" if scope else ""
    args = (scope,) if scope else ()
    now_s, now_e = month_bounds()
    py, pm = month_list(2)[0]
    prev_s, prev_e = mbounds(py, pm)

    cur = _flows(f"posted>=? AND posted<? {sc}", (*[now_s, now_e], *args))
    prv = _flows(f"posted>=? AND posted<? {sc}", (*[prev_s, prev_e], *args))

    bal = q1(
        f"SELECT COALESCE(SUM(balance),0) b FROM accounts WHERE archived=0 {'AND scope=?' if scope else ''}",
        args,
    )["b"]

    net_now = cur["income"] - cur["spend"]
    net_prev = prv["income"] - prv["spend"]
    return {
        "net_worth": round(bal, 2),
        "income_this_month": round(cur["income"], 2),
        "spend_this_month": round(cur["spend"], 2),
        "net_this_month": round(net_now, 2),
        "prev_net": round(net_prev, 2),
        "savings_rate": round(net_now / cur["income"], 4) if cur["income"] else None,
        "runway_months": (
            round(bal / cur["spend"], 1)
            if cur["spend"] > 0 and scope != "business"
            else None
        ),
    }


def net_worth_series(months=12, scope=None):
    """End-of-month balance per account type, reconstructed from current
    balances minus transaction flows since each month end."""
    rows = q("SELECT id, balance FROM accounts WHERE archived=0" + (" AND scope=?" if scope else ""), (scope,) if scope else ())
    total_bal = sum(r["balance"] for r in rows)
    tx = q(
        "SELECT posted, SUM(amount) a FROM transactions WHERE pending=0 AND is_transfer=0 AND posted<=date('now','localtime') "
        + ("AND scope=?" if scope else "")
        + " GROUP BY posted",
        (scope,) if scope else (),
    )
    by_day = defaultdict(float)
    for t in tx:
        by_day[t["posted"]] += t["a"]
    out = []
    for y, m in month_list(months):
        eom = date(y + (m == 12), (m % 12) + 1, 1).isoformat()  # first of next month
        future_flow = sum(a for d, a in by_day.items() if d >= eom)
        out.append({"month": f"{y}-{m:02d}", "balance": round(total_bal - future_flow, 2)})
    out[-1]["balance"] = round(total_bal, 2)
    return out


def cashflow_series(months=8, scope=None):
    sc = "AND scope=?" if scope else ""
    args = (scope,) if scope else ()
    out = []
    for y, m in month_list(months):
        s, e = mbounds(y, m)
        f = _flows(f"posted>=? AND posted<? {sc}", (s, e, *args))
        out.append({
            "month": f"{y}-{m:02d}",
            "label": calendar.month_abbr[m],
            "income": round(f["income"], 2),
            "spend": round(f["spend"], 2),
            "net": round(f["income"] - f["spend"], 2),
        })
    return out


def category_breakdown(scope=None, days=90, kind="expense"):
    since = (date.today() - timedelta(days=days)).isoformat()
    sign = "< 0" if kind == "expense" else "> 0"
    txs = q(f"""SELECT t.id,t.amount,t.category_id,COALESCE(c.name,'Uncategorized') name,
                       COALESCE(c.icon,'\U0001F4DD') icon,COALESCE(c.tax_deductible,0) td
                FROM transactions t LEFT JOIN categories c ON t.category_id=c.id
                WHERE t.pending=0 AND t.is_transfer=0 AND t.amount{sign} AND t.posted>=? AND t.posted<=date('now','localtime') {'AND t.scope=?' if scope else ''}""",
             (since, scope) if scope else (since,))
    amap = receipt_store.allocation_map([t["id"] for t in txs]) if kind == "expense" else {}
    grouped = {}
    for tx in txs:
        allocations = amap.get(tx["id"]) or [{"amount_cents": int(round(abs(tx["amount"]) * 100)), "category_id": tx["category_id"], "cat_name": tx["name"]}]
        for allocation in allocations:
            cid = allocation.get("category_id")
            cat = q1("SELECT name,icon,tax_deductible FROM categories WHERE id=?", (cid,)) if cid else None
            key = cid, (cat["name"] if cat else allocation.get("cat_name") or "Uncategorized")
            row = grouped.setdefault(key, {"name": key[1], "icon": (cat or {}).get("icon") or tx["icon"], "td": (cat or {}).get("tax_deductible", tx["td"]), "amt": 0, "n": 0})
            row["amt"] += allocation["amount_cents"] / 100
            row["n"] += 1
    rows = sorted(grouped.values(), key=lambda row: -row["amt"])
    tot = sum(r["amt"] for r in rows) or 1
    for r in rows:
        r["pct"] = round(r["amt"] / tot * 100, 1)
        r["amt"] = round(r["amt"], 2)
    return rows


# ---------------- budgets ----------------

def budget_status():
    s, e = month_bounds()
    budgets = q("""SELECT b.*, c.name cat_name, c.icon cat_icon
                   FROM budgets b LEFT JOIN categories c ON b.category_id=c.id""")
    out = []
    for b in budgets:
        w = "scope=?" if b["scope"] != "all" else "1=1"
        txs = q(
            f"SELECT id,amount,category_id FROM transactions WHERE pending=0 AND is_transfer=0 AND posted<=date('now','localtime') AND amount<0 AND posted>=? AND posted<? AND {w}",
            (s, e, b["scope"]) if b["scope"] != "all" else (s, e),
        )
        amap = receipt_store.allocation_map([t["id"] for t in txs])
        spent = 0
        for tx in txs:
            allocations = amap.get(tx["id"]) or [{"amount_cents": int(round(abs(tx["amount"]) * 100)), "category_id": tx["category_id"]}]
            spent += sum(a["amount_cents"] for a in allocations if a.get("category_id") == b["category_id"]) / 100
        out.append({
            **b,
            "spent": round(spent, 2),
            "pct": round(spent / b["month_limit"] * 100, 1) if b["month_limit"] else 0,
            "remaining": round(b["month_limit"] - spent, 2),
        })
    out.sort(key=lambda x: -x["pct"])
    return out


# ---------------- recurring detection ----------------

def detect_recurring():
    """Group normalized merchant names; flag those appearing >=3 months with similar amounts."""
    rows = q(
        """SELECT merchant, name, amount, posted, scope, category_id
           FROM transactions WHERE amount<0"""
    )
    groups = defaultdict(list)
    for t in rows:
        key = (t["merchant"] or t["name"]).lower().strip()[:28]
        groups[key].append(t)
    out = []
    today = date.today()
    for key, ts in groups.items():
        if len(ts) < 3:
            continue
        months = sorted({t["posted"][:7] for t in ts})
        # distinct recent months span
        span = len({m for m in months})
        amounts = [-t["amount"] for t in ts]
        avg = sum(amounts) / len(amounts)
        spread = (max(amounts) - min(amounts)) / avg if avg else 1
        recent = any(t["posted"] >= (today - timedelta(days=45)).isoformat() for t in ts)
        if span >= 3 and spread < 0.35 and recent:
            out.append({
                "merchant": ts[0]["merchant"] or ts[0]["name"],
                "avg_amount": round(avg, 2),
                "last_amount": round(amounts[0], 2),
                "times": len(ts),
                "months_seen": len(months),
                "scope": ts[0]["scope"],
                "category_id": ts[0]["category_id"],
                "monthly_cost": round(avg, 2),
            })
    out.sort(key=lambda x: -x["monthly_cost"])
    return out


def subscriptions_summary():
    import subscriptions
    return subscriptions.listing()


# ---------------- goals & business extras ----------------

def goal_projections():
    goals = q("SELECT * FROM goals ORDER BY completed_at IS NOT NULL, target_date IS NULL, target_date")
    out = []
    today = date.today()
    for g in goals:
        g = dict(g)
        remaining = max(g["target"] - g["saved"], 0)
        eta = None
        if g.get("monthly_plan") and g["monthly_plan"] > 0 and remaining > 0:
            months_left = remaining / g["monthly_plan"]
            eta_y, extra = divmod(int(today.month - 1 + round(months_left)), 12)
            eta_year = today.year + eta_y
            try:
                eta = date(eta_year, int(extra) + 1, 1).isoformat()
            except ValueError:
                eta = None
        on_track = bool(g["target_date"]) and (remaining == 0 or (eta is not None and eta <= g["target_date"]))
        out.append({**g, "remaining": round(remaining, 2), "eta": eta,
                    "on_track": on_track if g.get("target_date") else None,
                    "pct": round(min(g["saved"] / g["target"] * 100, 100), 1) if g["target"] else 0})
    return out


def business_summary():
    ov = overview("business")
    cats = category_breakdown("business", days=365, kind="expense")
    deductible = sum(c["amt"] for c in cats if c["td"])
    inc_rows = q(
        """SELECT COALESCE(c.name,'Other') name, SUM(t.amount) amt, COUNT(*) n
           FROM transactions t LEFT JOIN categories c ON t.category_id=c.id
           WHERE t.pending=0 AND t.is_transfer=0 AND t.posted<=date('now','localtime') AND t.scope='business' AND t.amount>0 AND t.posted>=?
           GROUP BY c.name ORDER BY amt DESC""",
        ((date.today() - timedelta(days=365)).isoformat(),),
    )
    cfg = q1("SELECT tax_rate_business FROM (SELECT ? tax_rate_business)", (_tax_rate(),))
    profit_ytd = sum(r["amt"] for r in inc_rows) - sum(c["amt"] for c in cats)
    top_clients = q(
        """SELECT name, COUNT(*) n, SUM(amount) amt FROM transactions
           WHERE pending=0 AND is_transfer=0 AND posted<=date('now','localtime') AND posted>=date('now','localtime','-365 days') AND scope='business' AND amount>0 GROUP BY name ORDER BY amt DESC LIMIT 5"""
    )
    return {
        "overview": ov,
        "expense_categories_12mo": cats,
        "deductible_12mo": round(deductible, 2),
        "income_sources_12mo": [{"name": r["name"], "amt": round(r["amt"], 2), "n": r["n"]} for r in inc_rows],
        "estimated_tax_setaside": round(max(profit_ytd, 0) * cfg["tax_rate_business"], 2),
        "profit_ttm": round(profit_ytd, 2),
        "top_clients": [{"name": r["name"], "n": r["n"], "amt": round(r["amt"], 2)} for r in top_clients],
    }


def _tax_rate():
    from db import get_config
    return get_config().get("tax_rate_business", 0.253)


def heatmap_data(scope=None, weeks=26):
    since = (date.today() - timedelta(weeks=weeks)).isoformat()
    rows = q(
        f"SELECT posted, SUM(-amount) v FROM transactions WHERE pending=0 AND is_transfer=0 AND posted<=date('now','localtime') AND amount<0 AND posted>=? {'AND scope=?' if scope else ''} GROUP BY posted",
        (since, scope) if scope else (since,),
    )
    return {r["posted"]: round(r["v"], 2) for r in rows}


def monthly_matrix(scope=None, months=6):
    """Category x month spend matrix for reports page."""
    cats = q(
        f"""SELECT DISTINCT COALESCE(c.name,'Uncategorized') name
            FROM transactions t LEFT JOIN categories c ON t.category_id=c.id
            WHERE t.pending=0 AND t.is_transfer=0 AND t.posted<=date('now','localtime') AND t.amount<0 {'AND t.scope=?' if scope else ''}""",
        (scope,) if scope else (),
    )
    names = [c["name"] for c in cats]
    series_out = {}
    for y, m in month_list(months):
        s, e = mbounds(y, m)
        rows = q(
            f"""SELECT t.id,t.amount,t.category_id,COALESCE(c.name,'Uncategorized') name
                FROM transactions t LEFT JOIN categories c ON t.category_id=c.id
                WHERE t.pending=0 AND t.is_transfer=0 AND t.posted<=date('now','localtime') AND t.amount<0 AND t.posted>=? AND t.posted<? {'AND t.scope=?' if scope else ''}
                """,
            (s, e, scope) if scope else (s, e),
        )
        amap = receipt_store.allocation_map([r["id"] for r in rows])
        monthly = defaultdict(float)
        for r in rows:
            allocations = amap.get(r["id"]) or [{"amount_cents": int(round(abs(r["amount"]) * 100)), "cat_name": r["name"]}]
            for allocation in allocations:
                monthly[allocation.get("cat_name") or "Uncategorized"] += allocation["amount_cents"] / 100
        for name, amount in monthly.items():
            series_out.setdefault(name, {})[f"{y}-{m:02d}"] = round(amount, 2)
    names = sorted(set(names) | set(series_out))
    return {"categories": names, "series": series_out}
