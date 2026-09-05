"""Deterministic cash, investment, debt, and inflation projections."""
from __future__ import annotations

import math
import db


FIELDS = ("years", "starting_cash", "starting_investments", "starting_debt", "monthly_savings", "monthly_investment", "monthly_debt_payment", "annual_return", "inflation", "debt_apr")
DEFAULTS = {"years": 10, "starting_cash": 0.0, "starting_investments": 0.0, "starting_debt": 0.0, "monthly_savings": 0.0, "monthly_investment": 0.0, "monthly_debt_payment": 0.0, "annual_return": 7.0, "inflation": 3.0, "debt_apr": 0.0}
MAX_INPUT = 1_000_000_000_000_000.0


def defaults(scope=None):
    """Return editable defaults seeded from current account balances."""
    if scope is not None and scope not in ("business", "personal"):
        raise ValueError("scope must be business or personal")
    args = (scope,) if scope else ()
    where = "archived=0" + (" AND scope=?" if args else "")
    rows = db.q("SELECT balance,type,subtype,name FROM accounts WHERE " + where, args)
    cash = investments = debt = 0.0
    for row in rows:
        bal = float(row.get("balance") or 0)
        account_type = str(row.get("type") or "").strip().lower()
        subtype = str(row.get("subtype") or "").strip().lower()
        # Classification comes from the account type metadata.  Merchant or
        # institution names are intentionally ignored: "Credit Union
        # checking" is still a depository account.
        is_investment = account_type == "investment" or subtype in {
            "brokerage", "401k", "403b", "ira", "roth ira", "securities",
        }
        if bal < 0:
            # Any negative balance is a liability, including an overdrawn
            # checking account and a negative investment account.
            debt += -bal
        elif is_investment:
            investments += bal
        else:
            # A positive credit/loan balance is a credit balance/asset.  Keep
            # the balance identity explicit: cash + investments - debt is the
            # sum of all account balances.
            cash += bal
    return {**DEFAULTS, "starting_cash": round(cash, 2), "starting_investments": round(investments, 2), "starting_debt": round(debt, 2), "scope": scope}


def _inputs(data):
    if not isinstance(data, dict): raise ValueError("projection inputs must be an object")
    out = dict(DEFAULTS)
    out.update({k: data[k] for k in FIELDS if k in data})
    for k in FIELDS:
        try: out[k] = float(out[k])
        except (TypeError, ValueError): raise ValueError(f"{k} must be finite")
        if not math.isfinite(out[k]): raise ValueError(f"{k} must be finite")
        if abs(out[k]) > MAX_INPUT: raise ValueError(f"{k} is outside the supported range")
    if out["years"] < 1 or out["years"] > 100 or out["years"] != int(out["years"]): raise ValueError("years must be an integer from 1 to 100")
    for k in FIELDS[1:]:
        if k != "annual_return" and out[k] < 0: raise ValueError(f"{k} cannot be negative")
    for k in ("annual_return", "inflation", "debt_apr"):
        if out[k] > 100 or (k == "annual_return" and out[k] <= -100): raise ValueError(f"{k} is outside the supported range")
    return out


def _scenario(inputs, annual_return):
    cash, investments, debt, contributions = inputs["starting_cash"], inputs["starting_investments"], inputs["starting_debt"], 0.0
    rows = []
    # The optimistic/conservative offsets can pass -100%.  Clamp the growth
    # factor to a tiny positive value so all scenarios remain real-valued and
    # finite while preserving the ordering of the scenarios.
    growth = max(1.0 + annual_return / 100.0, 1e-12)
    monthly_rate = growth ** (1 / 12) - 1
    # APR is nominal: divide the annual percentage by twelve for each month.
    debt_rate = inputs["debt_apr"] / 100 / 12
    for month in range(1, int(inputs["years"]) * 12 + 1):
        invest = inputs["monthly_investment"]
        debt_payment = min(inputs["monthly_debt_payment"], debt + debt * debt_rate)
        interest = debt * debt_rate
        debt = max(0.0, debt + interest - debt_payment)
        # Monthly savings is independent cash savings. Investment and debt
        # payments are separate allocations from income.
        cash += inputs["monthly_savings"]
        investments = investments * (1 + monthly_rate) + invest
        contributions += inputs["monthly_savings"] + invest
        if month % 12 == 0:
            year = month // 12
            nominal = cash + investments - debt
            values = (contributions, nominal, investments, cash, debt)
            if not all(math.isfinite(v) for v in values):
                raise ValueError("projection exceeds finite numeric bounds")
            rows.append({"year": year, "label": f"Year {year}", "contributions": round(contributions, 2), "value": round(nominal, 2), "investments": round(investments, 2), "cash": round(cash, 2), "debt": round(debt, 2)})
    return rows


def project(data):
    i = _inputs(data)
    conservative = _scenario(i, i["annual_return"] - 3)
    base = _scenario(i, i["annual_return"])
    optimistic = _scenario(i, i["annual_return"] + 3)
    rows = []
    for idx in range(len(base)):
        b, c, o = base[idx], conservative[idx], optimistic[idx]
        nominal = b["value"]
        inflation_factor = (1 + i["inflation"] / 100) ** b["year"]
        real = nominal / inflation_factor
        if not math.isfinite(real):
            raise ValueError("projection exceeds finite numeric bounds")
        rows.append({"year": b["year"], "label": b["label"], "contributions": b["contributions"], "conservative": c["value"], "base": nominal, "optimistic": o["value"], "investments": b["investments"], "cash": b["cash"], "debt": b["debt"], "real_value": round(real, 2)})
    final = rows[-1]
    return {"assumptions": i, "series": rows, "summary": {"years": int(i["years"]), "conservative": final["conservative"], "base": final["base"], "optimistic": final["optimistic"], "real_value": final["real_value"], "investments": final["investments"], "cash": final["cash"], "debt": final["debt"]}}
