"""Calendar-year and all-time spending reports."""
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import db
import receipt_store


def _cents(value):
    """Convert stored money to integer cents without binary-float drift."""
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return 0
    return int(amount * 100)


def _money(cents):
    return round(cents / 100, 2)


def _parse_as_of(as_of):
    if as_of is None:
        return date.today()
    if isinstance(as_of, date):
        return as_of
    try:
        return date.fromisoformat(str(as_of))
    except (TypeError, ValueError):
        raise ValueError("as_of must be YYYY-MM-DD")


def spending_report(year=None, scope=None, as_of=None):
    """Return one twelve-month spending report and all-time scope totals.

    ``as_of`` is an internal deterministic test seam; the HTTP endpoint uses
    today's local date. Transactions are intentionally read without joining
    account state, so archived-account history remains reportable.
    """
    today = _parse_as_of(as_of)
    current_year = today.year
    if scope not in (None, "personal", "business"):
        raise ValueError("scope must be personal or business")
    if year is None:
        report_year = current_year
    else:
        if isinstance(year, bool) or not isinstance(year, (int, str)) or (isinstance(year, str) and not year.isdigit()):
            raise ValueError("year must be an integer")
        report_year = int(year)
    if report_year < 1900 or report_year > current_year:
        raise ValueError(f"year must be between 1900 and {current_year}")

    where = ["t.amount < 0", "t.pending=0", "t.is_transfer=0", "t.posted <= ?"]
    args = [today.isoformat()]
    if scope:
        where.append("t.scope=?")
        args.append(scope)
    rows = db.q(
        """SELECT t.id,t.posted,t.amount,t.category_id,COALESCE(c.name,'Uncategorized') category_name
           FROM transactions t
           LEFT JOIN categories c ON c.id=t.category_id
           WHERE """ + " AND ".join(where),
        args,
    )

    allocation_rows = receipt_store.allocation_map([row.get("id") for row in rows])
    eligible = []
    for row in rows:
        try:
            posted = date.fromisoformat(str(row.get("posted")))
        except (TypeError, ValueError):
            continue
        parent = {
            "id": row.get("id"),
            "posted": posted,
            "cents": abs(_cents(row.get("amount"))),
            "category_id": row.get("category_id"),
            "category_name": row.get("category_name") or "Uncategorized",
        }
        # Child rows partition a parent charge.  The parent remains one
        # transaction for counts and all-time totals.
        splits = allocation_rows.get(parent["id"])
        parent["allocations"] = splits or [{
            "amount_cents": parent["cents"], "category_id": parent["category_id"],
            "cat_name": parent["category_name"],
        }]
        eligible.append(parent)
    eligible.sort(key=lambda row: row["posted"])

    month_cents = [0] * 12
    month_counts = [0] * 12
    category_cents = {}
    for row in eligible:
        if row["posted"].year != report_year:
            continue
        index = row["posted"].month - 1
        month_cents[index] += row["cents"]
        month_counts[index] += 1
        for allocation in row["allocations"]:
            key = (allocation.get("category_id"), allocation.get("cat_name") or "Uncategorized")
            category_cents.setdefault(key, [0] * 12)[index] += int(allocation["amount_cents"])

    months = [{
        "month": f"{report_year}-{month:02d}",
        "spend": _money(month_cents[month - 1]),
        "transaction_count": month_counts[month - 1],
        "is_future": report_year > current_year or (report_year == current_year and month > today.month),
    } for month in range(1, 13)]

    categories = []
    for (category_id, category_name), values in category_cents.items():
        categories.append({
            "id": category_id,
            "name": category_name,
            "months": [_money(value) for value in values],
            "total": _money(sum(values)),
        })
    categories.sort(key=lambda row: (-_cents(row["total"]), row["name"].lower(), str(row["id"] or "")))

    available = {current_year, report_year}
    # The API cannot select pre-1900 years, although those records remain in
    # all-time totals and still define the recorded date range.
    available.update(row["posted"].year for row in eligible if row["posted"].year >= 1900)
    return {
        "year": report_year,
        "as_of": today.isoformat(),
        "scope": scope,
        "available_years": sorted(available, reverse=True),
        "year_total": _money(sum(month_cents)),
        "all_time_total": _money(sum(row["cents"] for row in eligible)),
        "first_recorded_date": eligible[0]["posted"].isoformat() if eligible else None,
        "last_recorded_date": eligible[-1]["posted"].isoformat() if eligible else None,
        "transaction_count": len(eligible),
        "months": months,
        "categories": categories,
    }
