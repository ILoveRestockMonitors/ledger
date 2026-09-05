"""Cross-module invariants for receipt itemization and Plaid refreshes."""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import db
import plaid_client
import receipt_store
import reports


class ReceiptInvariantTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = db.DATA_DIR, db.DB_PATH, db.CONFIG_PATH
        db.DATA_DIR = self.tmp.name
        db.DB_PATH = os.path.join(self.tmp.name, "ledger.db")
        db.CONFIG_PATH = os.path.join(self.tmp.name, "config.json")
        db.init_db()
        receipt_store.init_schema()
        db.ex(
            "INSERT INTO items(id,institution,env,access_token,created_at) VALUES(?,?,?,?,?)",
            ("item", "Bank", "production", "access-token", "2026-01-01"),
        )
        db.ex(
            "INSERT INTO accounts(id,item_id,name,scope,balance,iso_currency,mask,plaid_account_id,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            ("account", "item", "Checking", "personal", 0, "USD", "1234", "plaid-account", "2026-01-01"),
        )
        db.ex(
            "INSERT INTO transactions(id,account_id,scope,amount,posted,name,merchant,category_id,created_at,plaid_transaction_id) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            ("tx", "account", "personal", -12.34, "2026-09-01", "AMZN Mktplace", "Amazon", "cat-shopping", "2026-09-01", "plaid-tx"),
        )

    def tearDown(self):
        db.DATA_DIR, db.DB_PATH, db.CONFIG_PATH = self.old
        self.tmp.cleanup()

    def _payload(self, order="same-order"):
        return {
            "status": "matched",
            "proposal": {
                "description": "Amazon mixed order",
                "match_confidence": 1.0,
                "receipt": {
                    "url": "https://www.amazon.com/gp/order-details/" + order,
                    "order_id": order,
                    "purchased_on": "2026-09-01",
                    "currency": "USD",
                    "total_cents": 1234,
                    "card_last4": "1234",
                },
                "items": [
                    {"description": "Groceries", "amount_cents": 500, "category_id": "cat-groceries", "confidence": 1.0},
                    {"description": "Shopping", "amount_cents": 734, "category_id": "cat-shopping", "confidence": 1.0},
                ],
            },
        }

    def _apply(self, order="same-order"):
        job = receipt_store.request("tx")
        claimed = receipt_store.claim_next()
        self.assertEqual(claimed["id"], job["id"])
        return receipt_store.finish(job["id"], self._payload(order), verified=True)

    def test_undo_releases_order_identity_before_same_order_relookup(self):
        self.assertEqual(self._apply()["status"], "applied")
        receipt_store.undo("tx")

        detail = receipt_store.detail("tx")
        self.assertEqual(detail["allocations"], [])
        self.assertEqual(detail["job"]["status"], "dismissed")
        self.assertIsNone(detail["job"]["receipt_order_id"])
        self.assertEqual(db.q1("SELECT category_id,category_override FROM transactions WHERE id='tx'"),
                         {"category_id": "cat-shopping", "category_override": None})

        second = receipt_store.request("tx")
        receipt_store.claim_next()
        self.assertEqual(receipt_store.finish(second["id"], self._payload(), verified=True)["status"], "applied")
        self.assertEqual(len(receipt_store.detail("tx")["allocations"]), 2)

    def test_report_category_totals_partition_parent_charge_once(self):
        self.assertEqual(self._apply()["status"], "applied")
        result = reports.spending_report(2026, as_of="2026-09-15")
        categories = {row["id"]: row["total"] for row in result["categories"]}
        self.assertEqual(result["year_total"], 12.34)
        self.assertEqual(categories["cat-groceries"], 5.0)
        self.assertEqual(categories["cat-shopping"], 7.34)
        self.assertEqual(sum(categories.values()), result["year_total"])

    def test_manual_category_can_be_replaced_explicitly_and_undo_restores_it(self):
        self._apply()
        receipt_store.manual_update("tx", {"category_id": "cat-groceries"})
        job = receipt_store.request("tx")
        receipt_store.claim_next()
        result = receipt_store.finish(job["id"], self._payload(), verified=True)
        self.assertEqual(result["status"], "review")
        self.assertEqual(receipt_store.review(job["id"], "accept")["status"], "applied")
        receipt_store.undo("tx")
        self.assertEqual(db.q1("SELECT category_id,category_override FROM transactions WHERE id='tx'"),
                         {"category_id": "cat-groceries", "category_override": 1})

    def test_manual_overrides_survive_modified_plaid_transaction(self):
        self.assertEqual(self._apply()["status"], "applied")
        receipt_store.manual_update("tx", {"category_id": "cat-groceries", "name": "My groceries", "scope": "business"})

        changes = {
            "added": [],
            "modified": [{
                "transaction_id": "plaid-tx", "account_id": "plaid-account", "amount": 12.34,
                "date": "2026-09-01", "name": "AMZN Mktplace",
                "personal_finance_category": {"primary": "GENERAL_MERCHANDISE", "detailed": "GENERAL_MERCHANDISE_OTHER"},
            }],
            "removed": [], "cursor": "next",
        }
        meta = {"accounts": [{"account_id": "plaid-account", "type": "depository", "balances": {"current": 0}}]}
        with patch.object(plaid_client, "sync_transactions", return_value=changes), patch.object(plaid_client, "fetch_accounts", return_value=meta):
            plaid_client.refresh_item("item")

        row = db.q1("SELECT category_id,category_override,name,name_override,scope,scope_override FROM transactions WHERE id='tx'")
        self.assertEqual((row["category_id"], row["category_override"], row["name"], row["name_override"], row["scope"], row["scope_override"]),
                         ("cat-groceries", 1, "My groceries", 1, "business", "business"))
        self.assertEqual(receipt_store.allocation_map(["tx"]), {})


if __name__ == "__main__":
    unittest.main()
