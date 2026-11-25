"""Tests for Amazon Business item-name matching and monthly budget category consolidation."""
import csv
import io
import os
import sys
import tempfile
import unittest
from datetime import date

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import amazon_business
import amazon_connector
import budget_consolidation
import category_rules
import db
import receipt_store
import server
import tx_names


def make_csv(rows, headers=None):
    buf = io.StringIO()
    wr = csv.writer(buf)
    wr.writerow(headers or [
        "Charge Identifier", "Payment Date", "Payment Amount", "Currency",
        "Payment Identifier", "Order ID", "Title", "Item Net Total",
        "Item Tax", "PO Line Item ID", "Transaction Type", "UNSPSC",
    ])
    wr.writerows(rows)
    return buf.getvalue()


class AmazonItemNameTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ctx = db.isolated_data(self.tmp.name)
        self.ctx.__enter__()
        db.init_db()
        receipt_store.init_schema()
        category_rules.init_schema()
        db.ex(
            "INSERT INTO accounts(id,name,scope,balance,iso_currency,mask,created_at) VALUES('chk','5/3 Business Checking','business',500,'USD','3297','2026-01-01')"
        )
        db.ex(
            "INSERT INTO accounts(id,name,scope,balance,iso_currency,mask,created_at) VALUES('pchk','5/3 Personal Checking','personal',500,'USD','7165','2026-01-01')"
        )

    def tearDown(self):
        self.ctx.__exit__(None, None, None)
        self.tmp.cleanup()

    def test_debit_card_tail_and_tax_columns_name_purchase_and_survive_category_edits(self):
        # Checking account mask is 3297, debit card in bank text is 6104, and category_override=1 is already set!
        db.ex(
            """INSERT INTO transactions(id,account_id,scope,amount,posted,name,merchant,category_id,category_override,created_at)
               VALUES('tx1','chk','business',-9.78,'2026-11-16',
               'DEBIT CARD PURCHASE AMAZON MKTPL*DF31I52N3 - 235251 440 TERRY AVE N SEATTLE WA ON 111326 FROM CARD#: XXXXXXXXXXX6104',
               'Amazon','cat-biz-supplies',1,'2026-11-16')"""
        )
        # Manual name_override=1 must NEVER be overwritten
        db.ex(
            """INSERT INTO transactions(id,account_id,scope,amount,posted,name,merchant,name_override,category_id,category_override,created_at)
               VALUES('tx_manual','chk','business',-32.29,'2026-10-26','128gb ssd','Amazon',1,'cat-biz-supplies',1,'2026-10-26')"""
        )
        csv_text = make_csv([
            [
                "DF31I52N3", "2026-11-15", "9.78", "USD", "Visa ****6104",
                "111-2222222-3333333",
                "Anker USB C to Ethernet Adapter, PowerExpand+ Aluminum Gigabit Adapter compatible with MacBook Pro",
                "9.00", "0.78", "line-1", "Charge", "",
            ],
            [
                "SSD999999", "2026-10-25", "32.29", "USD", "Visa ****6104",
                "111-4444444-5555555",
                "Kingston 128GB Internal SSD Drive",
                "32.29", "0.00", "line-1", "Charge", "43",
            ],
        ])
        amazon_connector.command("import", {"csv": csv_text})
        row1 = receipt_store.decorate_transactions([db.q1("SELECT * FROM transactions WHERE id='tx1'")])[0]
        self.assertEqual(row1["display_name"], "Anker USB C to Ethernet Adapter")
        self.assertEqual(row1["merchant"], "Amazon")

        # Changing category must NOT wipe out the matched item name!
        receipt_store.manual_update("tx1", {"category_id": "cat-biz-software"})
        row1_after = receipt_store.decorate_transactions([db.q1("SELECT * FROM transactions WHERE id='tx1'")])[0]
        self.assertEqual(row1_after["display_name"], "Anker USB C to Ethernet Adapter")
        self.assertEqual(row1_after["category_id"], "cat-biz-software")

        # Manual override stays untouched
        manual_row = receipt_store.decorate_transactions([db.q1("SELECT * FROM transactions WHERE id='tx_manual'")])[0]
        self.assertEqual(manual_row["display_name"], "128gb ssd")

    def test_pre_tax_report_without_tax_column_still_names_purchase(self):
        db.ex(
            """INSERT INTO transactions(id,account_id,scope,amount,posted,name,merchant,category_id,category_override,created_at)
               VALUES('tx_pretax','pchk','personal',-24.78,'2026-11-12',
               'DEBIT CARD PURCHASE AMAZON MKTPL*LZ2C590D3 FROM CARD#: XXXXXXXXXXX4071',
               'Amazon','cat-shopping',1,'2026-11-12')"""
        )
        # Net total is 22.99 while Payment Amount with tax is 24.78 (no Item Tax column)
        headers = ["Charge Identifier", "Payment Date", "Payment Amount", "Currency", "Payment Identifier", "Order ID", "Title", "Item Net Total"]
        csv_text = make_csv([
            ["LZ2C590D3", "2026-11-11", "24.78", "USD", "****4071", "112-1234567-7654321", "Insulated Stainless Water Bottle", "22.99"],
        ], headers=headers)
        amazon_connector.command("import", {"csv": csv_text})
        row = receipt_store.decorate_transactions([db.q1("SELECT * FROM transactions WHERE id='tx_pretax'")])[0]
        self.assertEqual(row["display_name"], "Insulated Stainless Water Bottle")

    def test_blink_subscription_is_cleaned_and_not_queued_as_amazon_order(self):
        self.assertEqual(tx_names.clean_merchant("BLINK AMZN.COM/BILL", "Amazon"), "Blink")
        self.assertIsNone(receipt_store.detect_provider({"name": "BLINK AMZN.COM/BILL", "merchant": "Blink"}))


class BudgetConsolidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ctx = db.isolated_data(self.tmp.name)
        self.ctx.__enter__()
        db.init_db()
        receipt_store.init_schema()
        category_rules.init_schema()
        db.ex("INSERT INTO accounts(id,name,scope,balance,created_at) VALUES('p','Personal','personal',1000,'2026-01-01')")
        db.ex("INSERT INTO accounts(id,name,scope,balance,created_at) VALUES('b','Business','business',1000,'2026-01-01')")
        # Personal budgets: Shopping ($200), Eat out ($300)
        db.ex("INSERT INTO budgets(id,category_id,scope,month_limit,period) VALUES('b_shop','cat-shopping','personal',200,'monthly')")
        db.ex("INSERT INTO budgets(id,category_id,scope,month_limit,period) VALUES('b_eat','cat-dining','personal',300,'monthly')")
        # Business budget: Software & SaaS ($300)
        db.ex("INSERT INTO budgets(id,category_id,scope,month_limit,period) VALUES('b_saas','cat-biz-software','business',300,'monthly')")

    def tearDown(self):
        self.ctx.__exit__(None, None, None)
        self.tmp.cleanup()

    def add_tx(self, tid, scope, category_id, amount=-25.0, posted="2026-11-15", transfer=0, matched_name=None):
        acct = "p" if scope == "personal" else "b"
        db.ex(
            """INSERT INTO transactions(id,account_id,scope,amount,posted,name,merchant,matched_name,category_id,is_transfer,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (tid, acct, scope, amount, posted, tid, tid, matched_name, category_id, transfer, posted),
        )

    def test_budgeted_categories_never_move_and_unbudgeted_consolidate_within_scope_for_month(self):
        # Already-budgeted categories (including Software & SaaS even on a personal row!) must NEVER move
        self.add_tx("t_saas_biz", "business", "cat-biz-software", -50)
        self.add_tx("t_saas_pers", "personal", "cat-biz-software", -3.47)
        self.add_tx("t_shop_pers", "personal", "cat-shopping", -40)

        # Unbudgeted personal in Nov 2026 -> Personal budgets
        self.add_tx("t_ent", "personal", "cat-fun", -25.90)          # Entertainment -> Shopping
        self.add_tx("t_groc", "personal", "cat-groceries", -30.00)   # Groceries -> Eat out

        # Unbudgeted business in Nov 2026 -> Business budgets (Software & SaaS right now)
        self.add_tx("t_office_biz", "business", "cat-biz-supplies", -80.00, matched_name="Printer Paper")
        self.add_tx("t_other_biz", "business", "cat-biz-other", -40.00)

        # October 2026 transaction must NOT be touched when consolidating November 2026!
        self.add_tx("t_oct_ent", "personal", "cat-fun", -15.00, posted="2026-10-20")
        # Transfer must NOT be touched!
        self.add_tx("t_xfer", "personal", "cat-fun", -100.00, transfer=1)

        prev = budget_consolidation.preview("2026-11", "everything", as_of=date(2026, 11, 24))
        by_key = {g["group_key"]: g for g in prev["groups"]}

        self.assertNotIn("personal:cat-biz-software", by_key)
        self.assertNotIn("business:cat-biz-software", by_key)
        self.assertNotIn("personal:cat-shopping", by_key)
        self.assertIn("Software & SaaS", prev["kept_budgeted_categories"])
        self.assertIn("Shopping", prev["kept_budgeted_categories"])

        self.assertEqual(by_key["personal:cat-fun"]["target_category_id"], "cat-shopping")
        self.assertEqual(by_key["personal:cat-groceries"]["target_category_id"], "cat-dining")
        self.assertEqual(by_key["business:cat-biz-supplies"]["target_category_id"], "cat-biz-software")
        self.assertEqual(by_key["business:cat-biz-other"]["target_category_id"], "cat-biz-software")
        self.assertEqual(prev["total_count"], 4)

        res = budget_consolidation.apply(prev["preview_id"])
        self.assertEqual(res["changed"], 4)

        # Verify Software & SaaS stayed Software & SaaS in BOTH scopes
        self.assertEqual(db.q1("SELECT category_id FROM transactions WHERE id='t_saas_pers'")["category_id"], "cat-biz-software")
        self.assertEqual(db.q1("SELECT category_id FROM transactions WHERE id='t_saas_biz'")["category_id"], "cat-biz-software")
        # Verify Nov unbudgeted moved cleanly while preserving matched_name
        office_after = db.q1("SELECT category_id, matched_name FROM transactions WHERE id='t_office_biz'")
        self.assertEqual((office_after["category_id"], office_after["matched_name"]), ("cat-biz-software", "Printer Paper"))
        self.assertEqual(db.q1("SELECT category_id FROM transactions WHERE id='t_ent'")["category_id"], "cat-shopping")
        self.assertEqual(db.q1("SELECT category_id FROM transactions WHERE id='t_groc'")["category_id"], "cat-dining")
        # Verify Oct & transfer untouched
        self.assertEqual(db.q1("SELECT category_id FROM transactions WHERE id='t_oct_ent'")["category_id"], "cat-fun")
        self.assertEqual(db.q1("SELECT category_id FROM transactions WHERE id='t_xfer'")["category_id"], "cat-fun")

        # Undo restores every row cleanly!
        undone = category_rules.undo(res["batch_id"])
        self.assertEqual(undone["restored"], 4)
        self.assertEqual(db.q1("SELECT category_id FROM transactions WHERE id='t_ent'")["category_id"], "cat-fun")
        self.assertEqual(db.q1("SELECT category_id FROM transactions WHERE id='t_office_biz'")["category_id"], "cat-biz-supplies")

    def test_adding_office_supplies_budget_keeps_office_supplies_and_reverses_shopping_entertainment(self):
        # Add Business budget on Office Supplies -> Office Supplies stays Office Supplies, Other Business -> Office Supplies!
        db.ex("INSERT INTO budgets(id,category_id,scope,month_limit,period) VALUES('b_off','cat-biz-supplies','business',150,'monthly')")
        # Swap Personal budget from Shopping to Entertainment -> Shopping moves into Entertainment!
        db.ex("DELETE FROM budgets WHERE id='b_shop'")
        db.ex("INSERT INTO budgets(id,category_id,scope,month_limit,period) VALUES('b_ent','cat-fun','personal',200,'monthly')")

        self.add_tx("t_off_biz", "business", "cat-biz-supplies", -60)
        self.add_tx("t_off_pers", "personal", "cat-biz-supplies", -32.98)
        self.add_tx("t_other_biz", "business", "cat-biz-other", -40)
        self.add_tx("t_shop_pers", "personal", "cat-shopping", -55)

        prev = budget_consolidation.preview("2026-11", "everything", as_of=date(2026, 11, 24))
        by_key = {g["group_key"]: g for g in prev["groups"]}

        # Office Supplies has a budget now -> stays as Office Supplies everywhere!
        self.assertNotIn("business:cat-biz-supplies", by_key)
        self.assertNotIn("personal:cat-biz-supplies", by_key)
        self.assertIn("Office Supplies", prev["kept_budgeted_categories"])
        # Other Business now routes to Office Supplies; Shopping routes to Entertainment!
        self.assertEqual(by_key["business:cat-biz-other"]["target_category_id"], "cat-biz-supplies")
        self.assertEqual(by_key["personal:cat-shopping"]["target_category_id"], "cat-fun")



    def test_amazon_business_orders_csv_without_charge_id(self):
        orders_csv = (
            "Order Date,Order ID,Title,Item Subtotal,Item Tax,Shipping,Payment Instrument Type,Currency\n"
            "2026-11-18,113-9988776-5544332,\"Logitech MX Master 3S Wireless Mouse - Ultra-Fast Scrolling, Ergonomic, 8K DPI, Quiet Clicks, Bluetooth\",89.99,7.42,0.00,Visa ending in 6104,USD\n"
        )
        parsed = amazon_business.parse_report(orders_csv)
        self.assertEqual(len(parsed["charges"]), 1)
        self.assertEqual(len(parsed["name_charges"]), 1)
        self.assertEqual(parsed["charges"][0]["amount_cents"], 9741)
        self.assertEqual(parsed["charges"][0]["card_last4"], "6104")
        tx = {
            "id": "tx-b2b-order",
            "account_id": "acc-p",
            "account_mask": "3297",
            "scope": "personal",
            "amount": -97.41,
            "posted": "2026-11-19",
            "name": "POS PURCHASE AMZN Mktp US FROM CARD#: XXXXXXXXXXX6104",
            "merchant": "Amazon",
            "iso_currency": "USD",
        }
        charge, method = amazon_business.select_charge(tx, parsed["name_charges"])
        self.assertIsNotNone(charge)
        self.assertEqual(amazon_business.format_purchase_name(charge["items"]), "Logitech MX Master 3S Wireless Mouse")


if __name__ == "__main__":
    unittest.main()
