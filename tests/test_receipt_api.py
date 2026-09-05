"""Purchase lookup boundaries: preview isolation and bounded settings."""
import os
import sys
import csv
import io
import tempfile
import unittest
from datetime import date
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "backend"))
import db
import receipt_service
import receipt_store
import server


class ReceiptApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.paths = (db.DATA_DIR, db.DB_PATH, db.CONFIG_PATH)
        db.DATA_DIR = self.tmp.name
        db.DB_PATH = os.path.join(self.tmp.name, "ledger.db")
        db.CONFIG_PATH = os.path.join(self.tmp.name, "config.json")
        db.init_db()
        self.handler = object.__new__(server.Handler)
        self.handler._json = lambda code, body: (code, body)

    def tearDown(self):
        db.DATA_DIR, db.DB_PATH, db.CONFIG_PATH = self.paths
        self.tmp.cleanup()

    def test_preview_cannot_dispatch_or_resume_even_production_looking_ids(self):
        with patch.object(server, "DEMO", True), patch.object(server.receipt_store, "request") as request, patch.object(server.receipt_store, "resume") as resume:
            for endpoint, body in (("request", {"transaction_id": "production-tx"}),
                                   ("resume", {"id": "production-job"})):
                with self.assertRaises(server.ApiError):
                    self.handler._api_post("/api/receipts/" + endpoint, body)
            request.assert_not_called()
            resume.assert_not_called()

    def test_lookup_preferences_require_real_booleans_and_bounded_integer(self):
        for field, values in (("enabled", ["false", 1, None]),
                              ("auto_apply", ["true", 0, None]),
                              ("daily_limit", [True, "10", 0, 31, 1.5])):
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    receipt_service.save_settings({field: value})
        self.assertEqual(receipt_service.save_settings({"auto_apply": False, "daily_limit": 3}),
                         {"enabled": False, "auto_apply": False, "daily_limit": 3})

    def test_generic_config_cannot_bypass_lookup_setting_validation(self):
        for key in ("receipt_lookup_enabled", "receipt_auto_apply", "receipt_daily_limit"):
            with self.assertRaises(ValueError):
                self.handler._api_post("/api/config", {key: True})
        self.assertFalse(db.get_config()["receipt_lookup_enabled"])

    def test_preview_never_probes_or_launches_merchant_worker(self):
        with patch.object(receipt_service.receipt_worker, "status") as readiness:
            self.assertFalse(receipt_service.status(demo=True)["ready"])
            readiness.assert_not_called()
        with patch.dict(os.environ, {"LEDGER_DEMO": "1"}), patch.object(receipt_service.receipt_store, "claim_next") as claim:
            self.assertIsNone(receipt_service.run_once())
            claim.assert_not_called()
            with self.assertRaises(ValueError):
                receipt_service.save_settings({"enabled": True})

    def _mixed_purchase(self):
        today = date.today().isoformat()
        db.ex("INSERT INTO accounts(id,name,scope,balance,mask,created_at) VALUES('a','Personal checking','personal',100,'1234',?)", (today,))
        db.ex("""INSERT INTO transactions(id,account_id,scope,amount,posted,name,merchant,category_id,created_at)
                 VALUES('mixed','a','personal',-50,?,'AMZN Mktp US','Amazon','cat-subscriptions',?)""", (today, today))
        receipt_store.init_schema()
        job = receipt_store.request("mixed")
        receipt_store.claim_next()
        proposal = {"description": "Amazon · toothbrush, groceries and car tools",
                    "ambiguous": False, "match_confidence": 1.0,
                    "receipt": {"url": "https://www.amazon.com/gp/css/order-details/", "order_id": "TEST-ORDER",
                                "purchased_on": today, "currency": "USD", "total_cents": 5000, "card_last4": "1234"},
                    "items": [{"description": name, "amount_cents": cents, "category_id": category, "confidence": 1.0}
                              for name, cents, category in (("Toothbrush", 1000, "cat-personal-care"),
                                                             ("Fresh groceries", 2500, "cat-groceries"),
                                                             ("Car tools", 1500, "cat-shopping"))]}
        result = receipt_store.finish(job["id"], {"status": "matched", "message": "Synthetic receipt", "proposal": proposal}, verified=True)
        self.assertEqual(result["status"], "applied")

    def test_invalid_worker_output_releases_running_job_without_changing_spend(self):
        self._mixed_purchase()
        receipt_store.undo("mixed")
        job = receipt_store.request("mixed")
        with patch.object(receipt_service, "disabled", return_value=False), \
             patch.object(receipt_service.receipt_store, "scan"), \
             patch.object(receipt_service.receipt_worker, "investigate", return_value={
                 "verified": True, "payload": {"status": "matched", "proposal": {"items": []}}
             }):
            result = receipt_service.run_once()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(receipt_store.detail("mixed")["allocations"], [])
        self.assertEqual(db.q1("SELECT amount FROM transactions WHERE id='mixed'")["amount"], -50)

    def test_category_filter_and_item_search_find_one_parent_purchase(self):
        self._mixed_purchase()
        for category in ("cat-personal-care", "cat-groceries", "cat-shopping"):
            self.handler.path = "/api/transactions?category_id=" + category
            code, body = self.handler._api("GET", "/api/transactions")
            self.assertEqual((code, body["total"], len(body["rows"])), (200, 1, 1))
            self.assertEqual(body["rows"][0]["amount"], -50)
        self.handler.path = "/api/transactions?category_id=cat-subscriptions"
        self.assertEqual(self.handler._api("GET", "/api/transactions")[1]["total"], 0)
        self.handler.path = "/api/transactions?search=Toothbrush"
        self.assertEqual(self.handler._api("GET", "/api/transactions")[1]["total"], 1)

    def test_csv_itemization_reconciles_to_original_bank_charge(self):
        self._mixed_purchase()
        self.handler._send = lambda code, body, ctype: body.decode()
        content = self.handler._api("GET", "/api/export/transactions.csv")
        rows = list(csv.DictReader(io.StringIO(content)))
        self.assertEqual(len(rows), 3)
        self.assertEqual(sum(float(row["amount"]) for row in rows), -50)
        self.assertEqual({row["category"] for row in rows}, {"Personal Care", "Groceries", "Shopping"})
        self.assertTrue(all(row["merchant"] == "Amazon" for row in rows))


if __name__ == "__main__":
    unittest.main()
