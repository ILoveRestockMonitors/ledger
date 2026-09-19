"""Focused integration coverage for account-free cash transactions."""
import io
import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from email.message import Message
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import analytics
import budget_overview
import category_rules
import db
import receipt_store
import reports
import server


class CashTransactions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = (db.DATA_DIR, db.DB_PATH, db.CONFIG_PATH)
        db.DATA_DIR = self.tmp.name
        db.DB_PATH = str(Path(self.tmp.name) / "ledger.db")
        db.CONFIG_PATH = str(Path(self.tmp.name) / "config.json")
        db.init_db()
        receipt_store.init_schema()
        category_rules.init_schema()
        db.ex(
            """INSERT INTO accounts(id,name,type,scope,balance,created_at)
               VALUES('wallet','Tracked wallet','depository','personal',100,'2026-01-01')"""
        )

    def tearDown(self):
        db.DATA_DIR, db.DB_PATH, db.CONFIG_PATH = self.old
        self.tmp.cleanup()

    def request(self, path, body=None, method=None):
        handler = object.__new__(server.Handler)
        handler.path = path
        handler.client_address = ("127.0.0.1", 1)
        handler.headers = Message()
        handler.headers["Host"] = "127.0.0.1:8907"
        handler.headers["X-Ledger-Request"] = "1"
        handler.headers["Content-Type"] = "application/json"
        raw = json.dumps(body).encode() if body is not None else b""
        handler.headers["Content-Length"] = str(len(raw))
        handler.rfile = io.BytesIO(raw)
        result = {}

        def send(code, payload, ctype="application/json"):
            result.update(code=code, content_type=ctype)
            result["body"] = json.loads(payload) if ctype == "application/json" else payload

        handler._send = send
        with (
            patch.object(server, "DEMO", True),
            patch.object(server, "PUBLIC_ORIGIN", ""),
            patch.object(server, "_scan_safely", return_value=None),
        ):
            handler._dispatch(method or ("POST" if body is not None else "GET"))
        return result

    def add_cash(self, **overrides):
        transaction = {
            "account_id": None,
            "scope": "personal",
            "amount": -12.34,
            "name": "Corner Shop",
            "posted": date.today().isoformat(),
            "category_id": "cat-groceries",
        }
        transaction.update(overrides)
        return self.request("/api/transactions", {"transaction": transaction})

    def test_cash_entry_reaches_spending_views_without_moving_balances(self):
        created = self.add_cash(scope="business")
        self.assertEqual(created["code"], 200, created)
        transaction_id = created["body"]["id"]
        row = db.q1("SELECT * FROM transactions WHERE id=?", (transaction_id,))
        self.assertIsNone(row["account_id"])
        self.assertEqual(row["scope"], "business")
        self.assertEqual(row["amount"], -12.34)
        self.assertEqual(db.q1("SELECT balance FROM accounts WHERE id='wallet'")["balance"], 100)

        filtered = self.request("/api/transactions?account_id=__cash__")
        self.assertEqual(filtered["body"]["total"], 1)
        self.assertEqual(filtered["body"]["rows"][0]["id"], transaction_id)
        self.assertEqual(analytics.overview("business")["spend_this_month"], 12.34)
        self.assertEqual(
            budget_overview.overview(date.today().strftime("%Y-%m"), "business")["summary"]["total"],
            12.34,
        )
        self.assertEqual(reports.spending_report(date.today().year, "business")["year_total"], 12.34)
        self.assertTrue(all(point["balance"] == 100 for point in analytics.net_worth_series(2)))

        exported = self.request("/api/export/transactions.csv")
        self.assertEqual(exported["code"], 200)
        self.assertIn(b"Cash / manual", exported["body"])

    def test_cash_entry_can_be_fully_edited_and_deleted(self):
        transaction_id = self.add_cash()["body"]["id"]
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        updated = self.request(
            "/api/transactions/update",
            {
                "id": transaction_id,
                "name": "Cash refund",
                "amount": 7.25,
                "posted": yesterday,
                "scope": "business",
                "is_transfer": False,
                "note": "Returned item",
            },
        )
        self.assertEqual(updated["code"], 200, updated)
        row = db.q1("SELECT * FROM transactions WHERE id=?", (transaction_id,))
        self.assertEqual(
            (row["name"], row["amount"], row["posted"], row["scope"], row["note"]),
            ("Cash refund", 7.25, yesterday, "business", "Returned item"),
        )
        self.assertEqual(self.request("/api/transactions?id=" + transaction_id, method="DELETE")["code"], 200)
        self.assertIsNone(db.q1("SELECT * FROM transactions WHERE id=?", (transaction_id,)))
        self.assertEqual(db.q1("SELECT balance FROM accounts WHERE id='wallet'")["balance"], 100)

    def test_account_backed_transaction_safety_is_unchanged(self):
        created = self.request(
            "/api/transactions",
            {"transaction": {"account_id": "wallet", "scope": "business", "amount": -5, "name": "Account purchase"}},
        )
        self.assertEqual(created["code"], 200, created)
        transaction_id = created["body"]["id"]
        self.assertEqual(db.q1("SELECT scope FROM transactions WHERE id=?", (transaction_id,))["scope"], "personal")
        self.assertEqual(db.q1("SELECT balance FROM accounts WHERE id='wallet'")["balance"], 95)

        rejected = self.request("/api/transactions/update", {"id": transaction_id, "amount": -50})
        self.assertEqual(rejected["code"], 400, rejected)
        self.assertEqual(db.q1("SELECT amount FROM transactions WHERE id=?", (transaction_id,))["amount"], -5)
        self.assertEqual(db.q1("SELECT balance FROM accounts WHERE id='wallet'")["balance"], 95)

    def test_cash_validation_and_same_name_category_preview(self):
        self.assertEqual(self.request("/api/transactions", {"transaction": {"amount": -3}})["code"], 400)
        self.assertEqual(self.add_cash(account_id="missing")["code"], 400)
        self.assertEqual(self.add_cash(amount=0)["code"], 400)
        self.assertEqual(self.add_cash(posted=(date.today() + timedelta(days=1)).isoformat())["code"], 400)

        anchor = self.add_cash(name="Market", category_id="cat-groceries")["body"]["id"]
        other = self.add_cash(name="Market", category_id="cat-shopping")["body"]["id"]
        preview = category_rules.preview(anchor, "cat-groceries")
        self.assertEqual(preview["count"], 1)
        self.assertEqual(preview["transactions"][0]["id"], other)
        self.assertEqual(preview["transactions"][0]["account_name"], "Cash / manual")


if __name__ == "__main__":
    unittest.main()
