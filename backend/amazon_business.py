"""Amazon Business charge reconciliation and item naming. No model, Codex or paid API is used."""
import csv
import io
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import db


def key(value):
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKC', str(value or '')).lower())


def cents(value):
    text = str(value or '').strip().replace(',', '')
    if text.startswith('(') and text.endswith(')'): text = '-' + text[1:-1]
    text = re.sub(r'^(?:USD\s*|\$)', '', text, flags=re.I).strip()
    if not re.fullmatch(r'-?\d+(?:\.\d{1,2})?', text): raise ValueError('Report contains an invalid money value.')
    try: return int(Decimal(text) * 100)
    except (InvalidOperation, OverflowError): raise ValueError('Report contains an invalid money value.') from None


def _opt_cents(value):
    text = str(value or '').strip()
    if not text:
        return 0
    return cents(text)


def iso_date(value):
    value = str(value or '').strip()
    if 'T' in value and len(value) >= 10:
        value = value[:10]
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%b %d, %Y', '%B %d, %Y'):
        try: return datetime.strptime(value, fmt).date().isoformat()
        except ValueError: pass
    raise ValueError('Report needs a valid Payment date or Transaction date.')


def card_tail(value):
    value = str(value or '').strip()
    if re.fullmatch(r'\d{4}', value): return value
    match = re.search(
        r'(?:ending\s+in|[*xX•]{2,}|(?:visa|mastercard|amex|american\s+express|discover|debit|credit|card)\s*[-–—:]\s*)\s*(\d{4})\b',
        value, re.I,
    )
    return match.group(1) if match else ''


def tx_cards(tx):
    """Return candidate 4-digit card/account masks for a bank transaction.

    Checking-account debit card purchases often carry the checking account mask
    in ``accounts.mask`` (e.g. 3297) while printing the debit card tail in the
    bank description (``FROM CARD#: XXXXXXXXXXX6104``).
    """
    cards = set()
    for field in ('mask', 'account_mask'):
        tail = card_tail(tx.get(field))
        if tail:
            cards.add(tail)
    raw_name = str(tx.get('name') or '')
    for match in re.findall(r'(?:from\s+card\s*#?\s*:?\s*[*xX•-]*|card\s*#?\s*:?\s*[*xX•]{2,}|ending\s+in\s+)(\d{4})\b', raw_name, re.I):
        cards.add(match)
    return cards


_SEO_SPLIT = re.compile(
    r'\s+(?:[-|–—])\s+|\s*;\s*|,'
    r'\s*(?:compatible\s+with|works\s+with|fits\s+|for\s+(?:iphone|ipad|macbook|samsung|android|pc|laptop|men|women|kids|dogs|cats|home|office))\b',
    re.I,
)


def clean_item_title(title, limit=68):
    """Shorten keyword-stuffed Amazon titles into a clean purchase label."""
    text = ' '.join(str(title or '').split()).strip(' -|,;:')
    if not text:
        return 'Amazon purchase'
    if len(text) <= limit:
        return text
    head = _SEO_SPLIT.split(text, 1)[0].strip(' -|,;:')
    if len(head) >= 12:
        text = head
    if len(text) > limit and ',' in text:
        parts = [p.strip() for p in text.split(',') if p.strip()]
        if parts and len(parts[0]) >= 14:
            text = parts[0]
        elif len(parts) >= 2 and len(parts[0] + ', ' + parts[1]) >= 14:
            text = parts[0] + ', ' + parts[1]
    if len(text) > limit:
        cut = text[:limit - 1].rsplit(' ', 1)[0]
        text = (cut if len(cut) >= 16 else text[:limit - 1]).rstrip(' -|,;:') + '…'
    return text


def format_purchase_name(items):
    """Build a concise transaction display name from one or more purchased items."""
    seen = []
    for item in items or []:
        raw = item.get('description') if isinstance(item, dict) else str(item or '')
        cleaned = clean_item_title(raw)
        if cleaned and cleaned.casefold() not in {s.casefold() for s in seen}:
            seen.append(cleaned)
    if not seen:
        return 'Amazon purchase'
    total_count = len(items or [])
    if len(seen) == 1:
        return f"{seen[0]} (×{total_count})" if total_count > 1 else seen[0]
    if len(seen) == 2 and total_count == 2:
        combined = f"{seen[0]}, {seen[1]}"
        if len(combined) <= 76:
            return combined
    return f"{seen[0]} (+{total_count - 1} more)"


def _parse_standard_order_csv(reader, fields):
    """Parse Amazon Business Orders CSVs and consumer Order History CSVs."""
    aliases = {
        "order": ("Order ID", "Amazon Order ID", "Order Number"),
        "date": ("Payment Date", "Shipment Date", "Ship Date"),
        "order_date": ("Order Date", "Transaction Date"),
        "gross": ("Total Owed", "Total Charged", "Item Total", "Order Item Total", "Line Total (Incl. Tax)"),
        "net": ("Item Subtotal", "Item Net Total", "Shipment Item Subtotal", "Net Total", "Line Item Total"),
        "tax": ("Item Tax", "Shipment Item Subtotal Tax", "Tax", "Sales Tax", "Estimated Tax"),
        "shipping": ("Shipping", "Item Shipping", "Shipping & Handling", "Shipping Charge"),
        "title": ("Title", "Product Name", "Product Title", "Item Description"),
        "card": ("Payment Instrument Last 4 Digits", "Payment Instrument Type", "Payment Instrument", "Payment Identifier", "Card Last 4"),
        "currency": ("Currency", "Currency Code", "Order Currency", "Payment Currency"),
        "asin": ("ASIN",),
        "unspsc": ("UNSPSC", "UNSPSC Code"),
        "category": ("GL Code", "Product Category", "Commodity"),
    }
    cols = {name: next((fields[key(a)] for a in names if key(a) in fields), None) for name, names in aliases.items()}
    if not (cols["order"] and (cols["date"] or cols["order_date"]) and (cols["gross"] or cols["net"]) and cols["title"]):
        return None
    pretax_only = bool(cols["net"] and not cols["gross"] and not cols["tax"])
    groups, skipped = {}, 0
    for index, raw in enumerate(reader):
        if index >= 50000:
            raise ValueError("Use a report with at most 50,000 rows.")
        row = {name: str(raw.get(col) or "").strip() if col else "" for name, col in cols.items()}
        if not any(row.values()):
            continue
        try:
            if row["gross"]:
                line_cents = cents(row["gross"])
            else:
                line_cents = cents(row["net"]) + _opt_cents(row["tax"]) + _opt_cents(row["shipping"])
            if line_cents <= 0:
                skipped += 1
                continue
            amt_str = row["gross"] or row["net"]
            currency = (row["currency"] or ("USD" if "$" in amt_str else "USD")).upper()
            if currency != "USD":
                skipped += 1
                continue
            try:
                when = iso_date(row["date"]) if row["date"] else iso_date(row["order_date"])
            except ValueError:
                when = iso_date(row["order_date"])
            card = card_tail(row["card"])
            if not re.fullmatch(r"\d{3}-\d{7}-\d{7}", row["order"]) or not row["title"]:
                skipped += 1
                continue
            gkey = (row["order"], when, card)
            group = groups.setdefault(gkey, {
                "charge_identifier": "",
                "posted": when,
                "amount_cents": 0,
                "card_last4": card,
                "currency": currency,
                "orders": [row["order"]],
                "items": [],
                **({"pretax_only": True} if pretax_only else {}),
            })
            group["amount_cents"] += line_cents
            group["items"].append({
                "description": row["title"][:300],
                "amount_cents": line_cents,
                "asin": row["asin"],
                "unspsc": row["unspsc"],
                "category_hint": row["category"],
            })
        except ValueError:
            skipped += 1
    result = [g for g in groups.values() if g["amount_cents"] > 0 and 0 < len(g["items"]) <= 100]
    if not result:
        raise ValueError("No USD Amazon orders could be read from this CSV.")
    reconciled = [g for g in result if g["card_last4"] and not g.get("pretax_only")]
    return {"charges": reconciled, "name_charges": result, "rejected_charges": 0, "skipped_rows": skipped}


def parse_report(text):
    """Read line-level reconciliation CSV; repeated payment amounts are not summed."""
    if not isinstance(text, str) or not text or len(text.encode()) > 12_000_000:
        raise ValueError('Use an Amazon Business reconciliation CSV smaller than 12 MB.')
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
    fields = {key(f): f for f in reader.fieldnames or []}
    if len(fields) != len(reader.fieldnames or []): raise ValueError('Report has duplicate column names.')
    aliases = {
        'charge': ('Charge Identifier', 'Charge ID', 'Payment Reference ID'),
        'date': ('Payment Date', 'Transaction Date', 'Charge Date', 'Shipment/Refund Date'),
        'amount': ('Payment Amount', 'Transaction Amount', 'Charge Amount'),
        'line_gross': ('Item Total', 'Order Item Total', 'Line Total (Incl. Tax)'),
        'line_total': ('Item Net Total', 'Net Total', 'Line Item Total', 'Item Subtotal'),
        'line_tax': ('Item Tax', 'Tax', 'Sales Tax', 'Estimated Tax'),
        'line_shipping': ('Shipping', 'Item Shipping', 'Shipping & Handling', 'Shipping Charge'),
        'title': ('Title', 'Product Title', 'Product Name', 'Item Description'),
        'order': ('Order ID', 'Amazon Order ID', 'Order Number'),
        'card': ('Payment Instrument Last 4 Digits', 'Payment Instrument Last4Digits', 'Card Last 4', 'Payment Identifier', 'Payment Instrument'),
        'currency': ('Currency', 'Currency Code', 'Payment Currency', 'Order Currency'),
        'type': ('Transaction Type',),
        'line': ('PO Line Item ID', 'Order Line Item ID', 'Line Item ID'),
        'invoice': ('Invoice Number', 'Invoice ID', 'Invoice or Credit Memo ID'),
        'shipment': ('Shipment ID', 'Shipment Number'),
        'asin': ('ASIN',), 'unspsc': ('UNSPSC', 'UNSPSC Code'),
        'category': ('GL Code', 'Product Category', 'Commodity'),
    }
    columns = {name: next((fields[key(a)] for a in names if key(a) in fields), None) for name, names in aliases.items()}
    if not columns['charge'] and not columns['amount']:
        fallback = _parse_standard_order_csv(reader, fields)
        if fallback is not None:
            return fallback
    has_line_amount = bool(columns['line_total'] or columns['line_gross'])
    required = ('charge', 'date', 'amount', 'title', 'order', 'card')
    missing = [aliases[name][0] for name in required if not columns[name]]
    if not has_line_amount:
        missing.insert(3, aliases['line_total'][0])
    if missing: raise ValueError('Add these columns to the reconciliation report: ' + ', '.join(missing) + '.')
    groups, rejected, skipped = {}, set(), 0
    for index, raw in enumerate(reader):
        if index >= 50000: raise ValueError('Use a report with at most 50,000 rows.')
        if None in raw: raise ValueError('Report rows do not match their column headers.')
        row = {name: str(raw.get(column) or '').strip() if column else '' for name, column in columns.items()}
        if not any(row.values()): continue
        if row['type'] and key(row['type']) not in ('charge', 'purchase'): skipped += 1; continue
        charge = row['charge'].upper()
        if not re.fullmatch(r'[A-Z0-9]{6,32}', charge): skipped += 1; continue
        if charge in rejected: continue
        try:
            amount = cents(row['amount'])
            net_cents = cents(row['line_total']) if row['line_total'] else 0
            gross_cents = cents(row['line_gross']) if row['line_gross'] else 0
            tax_cents = _opt_cents(row['line_tax']) + _opt_cents(row['line_shipping'])
            line_total = gross_cents if gross_cents > 0 else net_cents
            line_with_tax = net_cents + tax_cents if net_cents > 0 and tax_cents > 0 else line_total
            if amount <= 0 or line_total <= 0: skipped += 1; continue
            currency = row['currency'].upper()
            if not currency and '$' in row['amount']: currency = 'USD'
            if currency != 'USD': raise ValueError('Only explicitly USD reports are currently supported.')
            when, card = iso_date(row['date']), card_tail(row['card'])
            if not card: raise ValueError('Report needs the payment card last four digits.')
            if not re.fullmatch(r'\d{3}-\d{7}-\d{7}', row['order']) or not row['title']:
                raise ValueError('Report needs an order number and item title.')
            group = groups.setdefault(charge, {'charge_identifier': charge, 'posted': when, 'amount_cents': amount,
                                              'card_last4': card, 'currency': currency, 'orders': [], 'items': [], '_seen': {}})
            if (when, amount, card, currency) != (group['posted'], group['amount_cents'], group['card_last4'], group['currency']):
                raise ValueError('One charge has conflicting dates, amounts, currencies or cards.')
            identity = (row['order'], row['line'], row['invoice'], row['shipment']) if row['line'] else None
            signature = (row['title'], line_total, row['asin'], row['unspsc'])
            if identity and identity in group['_seen']:
                if group['_seen'][identity] == signature: continue
                raise ValueError('Report contains conflicting line items.')
            if identity: group['_seen'][identity] = signature
            if row['order'] not in group['orders']: group['orders'].append(row['order'])
            group['items'].append({'description': row['title'][:300], 'amount_cents': line_total,
                                   '_taxed_cents': line_with_tax,
                                   'asin': row['asin'], 'unspsc': row['unspsc'], 'category_hint': row['category']})
        except ValueError:
            rejected.add(charge); groups.pop(charge, None)
    result, name_only = [], []
    for charge, group in groups.items():
        group.pop('_seen')
        if len(group['items']) > 100 or not group['items']:
            rejected.add(charge); continue
        raw_sum = sum(item['amount_cents'] for item in group['items'])
        taxed_sum = sum(item.get('_taxed_cents', item['amount_cents']) for item in group['items'])
        if raw_sum != group['amount_cents'] and taxed_sum == group['amount_cents']:
            for item in group['items']:
                item['amount_cents'] = item['_taxed_cents']
            raw_sum = taxed_sum
        for item in group['items']:
            item.pop('_taxed_cents', None)
        if raw_sum != group['amount_cents']:
            rejected.add(charge)
            # Pre-tax Item Net Total exports (without an Item Tax column) or partial
            # promotional credits still identify the exact items purchased under this
            # Charge Identifier; keep them eligible for item-title naming only.
            # Allow pre-tax subtotal exports only within standard US sales-tax bounds (<=12%),
            # rejecting incomplete exports where a line item is missing.
            if raw_sum > 0 and not columns['line_tax'] and not columns['line_gross'] and raw_sum < group['amount_cents'] <= int(raw_sum * 1.12):
                name_only.append(group)
            continue
        result.append(group)
    if not result and not name_only:
        raise ValueError('No complete USD card charges could be verified. Include Charge Identifier, Payment Amount, Currency, card last four digits and line-item Net Total; line totals must equal each charge.')
    return {'charges': result, 'name_charges': result + name_only, 'rejected_charges': len(rejected), 'skipped_rows': skipped}


def sanitize_direct_charges(raw_list):
    """Validate direct Amazon Payments / Order Summary charges scraped under the user's login."""
    if not isinstance(raw_list, list):
        return []
    out = []
    for entry in raw_list[:500]:
        if not isinstance(entry, dict):
            continue
        try:
            when = iso_date(entry.get('posted'))
            amount = cents(entry.get('amount')) if 'amount' in entry else int(entry.get('amount_cents') or 0)
            if amount <= 0:
                continue
            card = card_tail(entry.get('card_last4') or entry.get('card'))
            order = str(entry.get('order_id') or '').strip()
            orders = [o for o in (entry.get('orders') or ([order] if order else [])) if re.fullmatch(r'\d{3}-\d{7}-\d{7}', str(o))]
            charge_id = str(entry.get('charge_identifier') or '').strip().upper()
            if charge_id and not re.fullmatch(r'[A-Z0-9]{6,32}', charge_id):
                charge_id = ''
            raw_items = entry.get('items') or []
            items = []
            for item in raw_items[:100]:
                desc = str(item.get('description') if isinstance(item, dict) else item or '').strip()[:300]
                if desc:
                    items.append({'description': desc, 'amount_cents': int(item.get('amount_cents') or 0) if isinstance(item, dict) else 0,
                                  'asin': '', 'unspsc': '', 'category_hint': ''})
            if not items or (not card and not charge_id and not orders):
                continue
            out.append({
                'charge_identifier': charge_id,
                'posted': when,
                'amount_cents': amount,
                'card_last4': card,
                'currency': 'USD',
                'orders': orders,
                'items': items,
            })
        except (ValueError, TypeError):
            continue
    return out


def references(tx):
    text = ' '.join(str(tx.get(k) or '') for k in ('name', 'merchant')).upper()
    refs = set(re.findall(r'\b\d{3}-\d{7}-\d{7}\b', text))
    refs.update(re.findall(r'(?:AMZN|AMAZON)[^*\n]{0,35}\*\s*([A-Z0-9]{6,32})\b', text))
    # Explicit reference labels can be supplied by a bank without an asterisk.
    refs.update(re.findall(r'(?:CHARGE\s*(?:ID|IDENTIFIER)|PAYMENT\s*REFERENCE)\s*[:#]?\s*([A-Z0-9]{6,32})\b', text))
    return refs


def select_charge(tx, charges, allow_cardless=False):
    amount, posted = cents(str(abs(tx['amount']))), date.fromisoformat(tx['posted'])
    currency = tx.get('currency') or tx.get('iso_currency') or 'USD'
    cards = tx_cards(tx)
    refs = references(tx)
    order_refs = {r for r in refs if re.fullmatch(r'\d{3}-\d{7}-\d{7}', r)}
    charge_refs = refs - order_refs
    candidates = []
    for charge in charges:
        if charge['currency'] != currency:
            continue
        if charge['amount_cents'] != amount:
            if not (charge.get('pretax_only') and charge['amount_cents'] <= amount <= int(charge['amount_cents'] * 1.12)):
                continue
        charge_card = charge.get('card_last4') or ''
        if charge_card:
            if not cards or charge_card not in cards:
                continue
        elif not allow_cardless:
            continue
        if abs((date.fromisoformat(charge['posted']) - posted).days) > 7:
            continue
        cid = charge.get('charge_identifier') or ''
        corders = charge.get('orders') or ()
        exact = bool(cid) and cid in charge_refs
        order = bool(order_refs.intersection(corders))
        if charge_refs and cid and not exact:
            continue
        if order_refs and corders and not order:
            continue
        method = 'charge_identifier' if exact else 'order_id' if order else ('amount_date' if not charge_card else 'amount_card_date')
        candidates.append((charge, method))
    exact = [row for row in candidates if row[1] == 'charge_identifier']
    if exact:
        candidates = exact
    else:
        card_matched = [row for row in candidates if row[1] != 'amount_date']
        if card_matched:
            candidates = card_matched
    return candidates[0] if len(candidates) == 1 else (None, 'ambiguous' if candidates else 'missing')


def apply_matched_names(conn, charges):
    """Set ``matched_name`` on every unambiguous Amazon purchase in SQLite.

    Preserves ``name_override=1`` manual edits and never alters amounts, dates,
    scopes, or categories. Returns count of updated rows.
    """
    if not charges:
        return 0
    cols = {r[1] for r in conn.execute('PRAGMA table_info(transactions)')}
    if 'matched_name' not in cols:
        conn.execute('ALTER TABLE transactions ADD COLUMN matched_name TEXT')
    rows = [dict(r) for r in conn.execute("""
        SELECT t.*, a.mask account_mask, a.iso_currency, COALESCE(a.archived, 0) archived
        FROM transactions t LEFT JOIN accounts a ON a.id = t.account_id
        WHERE t.amount < 0 AND COALESCE(t.pending, 0) = 0 AND COALESCE(t.is_transfer, 0) = 0
          AND COALESCE(a.archived, 0) = 0
          AND (lower(t.name) LIKE '%amazon%' OR lower(t.name) LIKE '%amzn%' OR lower(COALESCE(t.merchant, '')) = 'amazon')
    """).fetchall()]
    updated = 0
    for tx in rows:
        if tx.get('name_override'):
            continue
        charge, method = select_charge(tx, charges, allow_cardless=True)
        if not charge:
            continue
        # Ensure no peer transaction claims the same charge ambiguously.
        collision = False
        for peer in rows:
            if peer['id'] == tx['id'] or peer['amount'] != tx['amount']:
                continue
            if abs((date.fromisoformat(peer['posted']) - date.fromisoformat(tx['posted'])).days) > 7:
                continue
            selected, peer_method = select_charge(peer, [charge], allow_cardless=True)
            if selected and (method != 'charge_identifier' or peer_method == 'charge_identifier'):
                collision = True
                break
        if collision:
            continue
        label = format_purchase_name(charge.get('items') or [])[:300]
        if label and tx.get('matched_name') != label:
            conn.execute('UPDATE transactions SET matched_name=? WHERE id=? AND COALESCE(name_override, 0)=0', (label, tx['id']))
            updated += 1
    return updated


def item_category(item, scope):
    categories = db.q("SELECT id,name FROM categories WHERE kind='expense'")
    learned = db.q('''SELECT DISTINCT ra.category_id FROM receipt_allocations ra JOIN transactions t ON t.id=ra.transaction_id
                     WHERE ra.active=1 AND ra.manual_category=1 AND t.scope=? AND ra.description=? AND ra.category_id IS NOT NULL''',
                   (scope, item['description']))
    valid = {c['id'] for c in categories}
    if len(learned) == 1 and learned[0]['category_id'] in valid: return learned[0]['category_id'], 1.0
    if len(learned) > 1: return None, 0
    hint = key(item.get('category_hint'))
    exact = [c['id'] for c in categories if key(c['name']) == hint and hint]
    if len(exact) == 1: return exact[0], .98
    code = re.sub(r'\D', '', item.get('unspsc') or '')
    names = []
    if code.startswith('44'): names = ['Office Supplies']
    elif code.startswith('43'): names = ['Hardware & Equipment'] if scope == 'business' else []
    elif code.startswith('50'): names = ['Groceries']
    elif code.startswith('531316'): names = ['Personal Care']
    elif re.search(r'\b(?:printer paper|copy paper|ballpoint pens?|printer ink|toner cartridge|sticky notes)\b', item['description'], re.I): names = ['Office Supplies']
    elif re.search(r'\b(?:shampoo|toothpaste|deodorant|body wash)\b', item['description'], re.I): names = ['Personal Care']
    elif re.search(r'\b(?:dog food|cat food|cat litter)\b', item['description'], re.I): names = ['Kids & Pets']
    chosen = next((c['id'] for name in names for c in categories if key(c['name']) == key(name)), None)
    return chosen, .96 if chosen else 0


def proposal(tx, charge, method):
    items = []
    for i, item in enumerate(charge['items']):
        category, confidence = item_category(item, tx.get('scope', 'business'))
        items.append({'line_key': str(i), 'description': item['description'], 'amount_cents': item['amount_cents'],
                      'category_id': category, 'confidence': confidence})
    return {'description': format_purchase_name(charge['items'])[:300],
            'match_confidence': 1.0 if method == 'charge_identifier' else .90,
            'match_method': method, 'items': items,
            'receipt': {'source': 'amazon-business', 'url': 'https://www.amazon.com/b2b/aba/reports',
                        'order_id': ', '.join(charge['orders']), 'charge_identifier': charge['charge_identifier'],
                        'purchased_on': charge['posted'], 'currency': charge['currency'],
                        'total_cents': charge['amount_cents'], 'card_last4': charge['card_last4']}}
