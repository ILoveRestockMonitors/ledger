"""Calendar-year and all-time spending report tests."""
import io
import json
import os
import sys
import tempfile
import unittest
from email.message import Message
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import db
import reports
import server


class SpendingReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = (db.DATA_DIR, db.DB_PATH, db.CONFIG_PATH)
        db.DATA_DIR = self.tmp.name
        db.DB_PATH = os.path.join(self.tmp.name, "ledger.db")
        db.CONFIG_PATH = os.path.join(self.tmp.name, "config.json")
        db.init_db()
        db.ex("INSERT INTO accounts(id,name,type,scope,balance,archived,created_at) VALUES(?,?,?,?,?,?,?)", ("personal", "Personal", "depository", "personal", 0, 0, "2010-01-01"))
        db.ex("INSERT INTO accounts(id,name,type,scope,balance,archived,created_at) VALUES(?,?,?,?,?,?,?)", ("archived", "Archived business", "depository", "personal", 0, 1, "2010-01-01"))
        self._tx("old", "personal", "personal", "2010-01-01", -1.11, "cat-groceries")
        self._tx("ancient", "personal", "personal", "1899-01-01", -9.99, "cat-shopping")
        self._tx("dec", "personal", "personal", "2025-12-31", -2.22, "cat-shopping")
        self._tx("jan", "personal", "personal", "2026-01-01", -10.01, "cat-groceries")
        self._tx("leap", "personal", "personal", "2024-02-29", -20.02, "cat-groceries")
        self._tx("cents", "personal", "personal", "2026-03-01", -0.03, None)
        # Transaction scope is authoritative even when its account scope is
        # different, and archived account history remains reportable.
        self._tx("archived", "archived", "business", "2026-08-15", -5.00, "cat-shopping")
        self._tx("future-current-month", "personal", "personal", "2026-09-20", -7.77, "cat-shopping")
        self._tx("future", "personal", "personal", "2026-10-01", -99.99, "cat-shopping")
        self._tx("pending", "personal", "personal", "2026-04-01", -30.00, "cat-shopping", pending=1)
        self._tx("transfer", "personal", "personal", "2026-05-01", -40.00, "cat-shopping", is_transfer=1)
        self._tx("income", "personal", "personal", "2026-06-01", 100.00, "cat-income")

    def tearDown(self):
        db.DATA_DIR, db.DB_PATH, db.CONFIG_PATH = self.old
        self.tmp.cleanup()

    def _tx(self, tid, account, scope, posted, amount, category, pending=0, is_transfer=0):
        db.ex("INSERT INTO transactions(id,account_id,scope,amount,posted,name,merchant,category_id,pending,is_transfer,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (tid, account, scope, amount, posted, tid, tid, category, pending, is_transfer, posted))

    def test_calendar_and_all_time_totals_include_archived_and_reconcile_cents(self):
        result = reports.spending_report(2026, "personal", as_of="2026-09-15")
        self.assertEqual(result["year_total"], 10.04)
        self.assertEqual(result["all_time_total"], 43.38)
        self.assertEqual((result["first_recorded_date"], result["last_recorded_date"], result["transaction_count"]), ("1899-01-01", "2026-03-01", 6))
        self.assertEqual(result["available_years"], [2026, 2025, 2024, 2010])
        self.assertEqual(result["months"][0], {"month": "2026-01", "spend": 10.01, "transaction_count": 1, "is_future": False})
        self.assertEqual(result["months"][1]["spend"], 0)
        self.assertEqual(result["months"][8], {"month": "2026-09", "spend": 0, "transaction_count": 0, "is_future": False})
        self.assertEqual(result["months"][9], {"month": "2026-10", "spend": 0, "transaction_count": 0, "is_future": True})
        self.assertEqual(sum(item["spend"] for item in result["months"]), result["year_total"])
        self.assertEqual(sum(item["total"] for item in result["categories"]), result["year_total"])

        december = reports.spending_report(2025, "personal", as_of="2026-09-15")
        self.assertEqual(december["year_total"], 2.22)
        self.assertEqual(december["months"][11]["spend"], 2.22)
        leap = reports.spending_report(2024, "personal", as_of="2026-09-15")
        self.assertEqual(leap["year_total"], 20.02)
        self.assertEqual(leap["months"][1]["spend"], 20.02)

    def test_all_scope_includes_archived_business_transaction_and_excludes_non_spend(self):
        result = reports.spending_report(2026, as_of="2026-09-15")
        self.assertEqual(result["year_total"], 15.04)
        self.assertEqual(result["all_time_total"], 48.38)
        self.assertEqual(result["transaction_count"], 7)
        self.assertEqual(next(item for item in result["months"] if item["month"] == "2026-08")["spend"], 5.0)

    def test_business_only_filter_uses_transaction_scope(self):
        result = reports.spending_report(2026, "business", as_of="2026-09-15")
        self.assertEqual((result["year_total"], result["all_time_total"], result["transaction_count"]), (5.0, 5.0, 1))
        self.assertEqual((result["first_recorded_date"], result["last_recorded_date"]), ("2026-08-15", "2026-08-15"))

    def test_empty_year_and_available_year_request(self):
        result = reports.spending_report(2023, "personal", as_of="2026-09-15")
        self.assertEqual(result["year_total"], 0)
        self.assertEqual(result["categories"], [])
        self.assertEqual(result["available_years"], [2026, 2025, 2024, 2023, 2010])
        self.assertTrue(all(month["spend"] == 0 and month["transaction_count"] == 0 for month in result["months"]))
        self.assertTrue(all(not month["is_future"] for month in result["months"]))

    def test_invalid_scope_or_year_is_rejected(self):
        with self.assertRaises(ValueError): reports.spending_report(2026, "household", as_of="2026-09-15")
        with self.assertRaises(ValueError): reports.spending_report(1899, as_of="2026-09-15")
        with self.assertRaises(ValueError): reports.spending_report(2027, as_of="2026-09-15")
        with self.assertRaises(ValueError): reports.spending_report("2026x", as_of="2026-09-15")
        with self.assertRaises(ValueError): reports.spending_report(2026.0, as_of="2026-09-15")

    def test_empty_dataset_has_null_range_and_zero_months(self):
        db.ex("DELETE FROM transactions")
        result = reports.spending_report(2026, as_of="2026-09-15")
        self.assertEqual((result["year_total"], result["all_time_total"], result["transaction_count"]), (0, 0, 0))
        self.assertEqual((result["first_recorded_date"], result["last_recorded_date"]), (None, None))
        self.assertTrue(all(month["spend"] == 0 and month["transaction_count"] == 0 for month in result["months"]))

    def test_http_endpoint_defaults_and_returns_400_for_invalid_query(self):
        def request(path):
            handler = object.__new__(server.Handler)
            handler.path = path
            handler.client_address = ("127.0.0.1", 1)
            handler.headers = Message()
            handler.headers["Host"] = "127.0.0.1:8907"
            handler.headers["X-Ledger-Request"] = "1"
            result = {}
            handler._send = lambda code, body, ctype="application/json": result.update(code=code, body=json.loads(body))
            with patch.object(server, "DEMO", True), patch.object(server, "PUBLIC_ORIGIN", ""), patch.object(reports, "date", type("FixedDate", (object,), {"today": staticmethod(lambda: __import__("datetime").date(2026, 9, 15)), "fromisoformat": staticmethod(__import__("datetime").date.fromisoformat)})):
                handler._dispatch("GET")
            return result

        default = request("/api/reports/spending")
        self.assertEqual((default["code"], default["body"]["year"], default["body"]["scope"]), (200, 2026, None))
        self.assertEqual(request("/api/reports/spending?year=2026&scope=invalid")["code"], 400)
        self.assertEqual(request("/api/reports/spending?year=2027")["code"], 400)


if __name__ == "__main__":
    unittest.main()
