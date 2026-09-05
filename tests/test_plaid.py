"""Focused Plaid persistence tests using mocked HTTP responses."""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import db
import plaid_client
import subscriptions
import cancellations


class PlaidPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = (db.DATA_DIR, db.DB_PATH, db.CONFIG_PATH)
        db.DATA_DIR = self.tmp.name
        db.DB_PATH = os.path.join(self.tmp.name, "ledger.db")
        db.CONFIG_PATH = os.path.join(self.tmp.name, "config.json")
        db.init_db()
        subscriptions.init_schema()
        cancellations.init_schema()
        columns = {row[1] for row in db._conn().execute("PRAGMA table_info(transactions)")}
        c = db._conn()
        try:
            if "is_transfer_override" not in columns:
                c.execute("ALTER TABLE transactions ADD COLUMN is_transfer_override INTEGER")
            if "scope_override" not in columns:
                c.execute("ALTER TABLE transactions ADD COLUMN scope_override TEXT")
            c.commit()
        finally:
            c.close()
        db.save_config({"plaid_client_id": "client", "plaid_secret": "secret", "plaid_env": "sandbox"})

    def tearDown(self):
        db.DATA_DIR, db.DB_PATH, db.CONFIG_PATH = self.old
        self.tmp.cleanup()

    def test_repeated_exchange_reuses_plaid_item_and_account_ids(self):
        responses = {
            "/item/public_token/exchange": {"access_token": "access", "item_id": "plaid-item"},
            "/accounts/get": {"accounts": [{
                "account_id": "plaid-account", "name": "Checking", "type": "depository",
                "balances": {"current": 100, "iso_currency_code": "USD"},
            }]},
        }

        def fake_post(path, payload, env=None):
            return responses[path]

        with patch.object(plaid_client, "_post", side_effect=fake_post):
            item_id, first = plaid_client.ingest_item(public_token="public", institution="Bank")
            reused_id, second = plaid_client.ingest_item(public_token="public", institution="Bank", scope="business", existing_item_id=item_id)
            deduped_id, third = plaid_client.ingest_item(public_token="public", institution="Bank")

        self.assertEqual(reused_id, item_id)
        self.assertEqual(deduped_id, item_id)
        self.assertEqual(first[0]["id"], second[0]["id"])
        self.assertEqual(second[0]["id"], third[0]["id"])
        self.assertEqual(db.q1("SELECT COUNT(*) n FROM items")["n"], 1)
        self.assertEqual(db.q1("SELECT COUNT(*) n FROM accounts")["n"], 1)
        # The local scope is a user choice and survives a reconnect.
        self.assertEqual(db.q1("SELECT scope FROM accounts")["scope"], "personal")

    def test_modified_transaction_reconciles_account_scope_and_transfer(self):
        db.ex("INSERT INTO items(id,institution,env,access_token,created_at) VALUES(?,?,?,?,?)", ("item", "Bank", "sandbox", "access", "2026-01-01"))
        db.ex("INSERT INTO accounts(id,item_id,name,type,scope,balance,plaid_account_id,created_at) VALUES(?,?,?,?,?,?,?,?)", ("a1", "item", "Checking", "depository", "personal", 0, "p1", "2026-01-01"))
        db.ex("INSERT INTO accounts(id,item_id,name,type,scope,balance,plaid_account_id,created_at) VALUES(?,?,?,?,?,?,?,?)", ("a2", "item", "Business", "depository", "business", 0, "p2", "2026-01-01"))
        db.ex("INSERT INTO transactions(id,account_id,scope,amount,posted,name,pending,plaid_transaction_id,created_at,is_transfer) VALUES(?,?,?,?,?,?,?,?,?,?)", ("tx", "a1", "personal", -10, "2026-09-01", "Payment", 0, "plaid-tx", "2026-09-01", 0))
        changes = {"added": [], "modified": [{
            "transaction_id": "plaid-tx", "account_id": "p2", "amount": 10,
            "date": "2026-09-01", "name": "Payment",
            "personal_finance_category": {"primary": "TRANSFER_IN", "detailed": "TRANSFER_IN"},
        }], "removed": [], "cursor": "next"}
        meta = {"accounts": [
            {"account_id": "p1", "type": "depository", "balances": {"current": 0}},
            {"account_id": "p2", "type": "depository", "balances": {"current": 0}},
        ]}
        with patch.object(plaid_client, "sync_transactions", return_value=changes), patch.object(plaid_client, "fetch_accounts", return_value=meta):
            plaid_client.refresh_item("item")

        row = db.q1("SELECT account_id,scope,amount,is_transfer FROM transactions WHERE id='tx'")
        self.assertEqual((row["account_id"], row["scope"], row["amount"], row["is_transfer"]), ("a2", "business", -10.0, 1))

    def test_modified_transaction_preserves_manual_scope_and_transfer_overrides(self):
        db.ex("INSERT INTO items(id,institution,env,access_token,created_at) VALUES(?,?,?,?,?)", ("item", "Bank", "sandbox", "access", "2026-01-01"))
        db.ex("INSERT INTO accounts(id,item_id,name,type,scope,balance,plaid_account_id,created_at) VALUES(?,?,?,?,?,?,?,?)", ("a1", "item", "Checking", "depository", "personal", 0, "p1", "2026-01-01"))
        db.ex("INSERT INTO accounts(id,item_id,name,type,scope,balance,plaid_account_id,created_at) VALUES(?,?,?,?,?,?,?,?)", ("a2", "item", "Business", "depository", "business", 0, "p2", "2026-01-01"))
        db.ex("INSERT INTO transactions(id,account_id,scope,scope_override,amount,posted,name,pending,plaid_transaction_id,created_at,is_transfer,is_transfer_override) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", ("tx", "a1", "personal", "personal", -10, "2026-09-01", "Payment", 0, "plaid-tx", "2026-09-01", 0, 0))
        changes = {"added": [], "modified": [{
            "transaction_id": "plaid-tx", "account_id": "p2", "amount": 10,
            "date": "2026-09-01", "name": "Payment",
            "personal_finance_category": {"primary": "TRANSFER_IN", "detailed": "TRANSFER_IN"},
        }], "removed": [], "cursor": "next"}
        meta = {"accounts": [
            {"account_id": "p1", "type": "depository", "balances": {"current": 0}},
            {"account_id": "p2", "type": "depository", "balances": {"current": 0}},
        ]}
        with patch.object(plaid_client, "sync_transactions", return_value=changes), patch.object(plaid_client, "fetch_accounts", return_value=meta):
            plaid_client.refresh_item("item")

        row = db.q1("SELECT account_id,scope,amount,is_transfer FROM transactions WHERE id='tx'")
        self.assertEqual((row["account_id"], row["scope"], row["amount"], row["is_transfer"]), ("a2", "personal", -10.0, 0))

    def test_existing_item_id_mismatch_is_rejected_transactionally(self):
        db.ex("INSERT INTO items(id,plaid_item_id,institution,env,access_token,created_at) VALUES(?,?,?,?,?,?)", ("local", "old-plaid-item", "Bank", "sandbox", "old-access", "2026-01-01"))

        def fake_post(path, payload, env=None):
            if path == "/item/public_token/exchange":
                return {"access_token": "new-access", "item_id": "new-plaid-item"}
            if path == "/accounts/get":
                return {"accounts": [{"account_id": "new-account", "type": "depository", "balances": {"current": 25}}]}
            raise AssertionError(path)

        with patch.object(plaid_client, "_post", side_effect=fake_post):
            with self.assertRaises(plaid_client.PlaidError):
                plaid_client.ingest_item(public_token="public", existing_item_id="local")
        self.assertEqual(db.q1("SELECT COUNT(*) n FROM items")["n"], 1)
        self.assertEqual(db.q1("SELECT plaid_item_id,access_token FROM items WHERE id='local'"), {"plaid_item_id": "old-plaid-item", "access_token": "old-access"})
        self.assertEqual(db.q1("SELECT COUNT(*) n FROM accounts")["n"], 0)

    def test_remove_item_detaches_subscription_with_scope_wide_identity(self):
        db.ex("INSERT INTO items(id,plaid_item_id,institution,env,access_token,created_at) VALUES(?,?,?,?,?,?)", ("item", "plaid-item", "Bank", "sandbox", "access", "2026-01-01"))
        db.ex("INSERT INTO accounts(id,item_id,name,type,scope,balance,plaid_account_id,created_at) VALUES(?,?,?,?,?,?,?,?)", ("account", "item", "Checking", "depository", "personal", 0, "plaid-account", "2026-01-01"))
        sub = subscriptions.save({"merchant": "Detached SaaS", "scope": "personal", "account_id": "account", "amount": 20, "cadence": "monthly", "next_due": "2026-09-01", "status": "active"})
        old_key = sub["normalized_key"]
        db.ex("INSERT INTO subscription_learning(normalized_key,decision,updated_at) VALUES(?,?,?)", (old_key, "confirm", "2026-01-01"))
        with patch.object(plaid_client, "_post", return_value={}):
            plaid_client.remove_item("item")
        detached = db.q1("SELECT account_id,source,normalized_key FROM subscriptions WHERE id=?", (sub["id"],))
        self.assertEqual((detached["account_id"], detached["source"], detached["normalized_key"]), (None, "manual", "detached saas|personal|"))
        self.assertEqual(db.q1("SELECT normalized_key FROM subscription_learning WHERE normalized_key=?", ("detached saas|personal|",))["normalized_key"], "detached saas|personal|")

    def test_manual_price_review_uses_latest_charge(self):
        sub = subscriptions.save({"merchant": "Manual SaaS", "scope": "personal", "amount": 20, "cadence": "monthly", "next_due": "2026-09-01", "status": "active"})
        for idx, amount in enumerate((20, 20, 40)):
            db.ex("INSERT INTO transactions(id,account_id,scope,amount,posted,name,merchant,created_at) VALUES(?,?,?,?,?,?,?,?)", (f"tx{idx}", None, "personal", -amount, f"2026-0{7+idx}-04", "Manual SaaS", "Manual SaaS", f"2026-0{7+idx}-04"))
        result = subscriptions.scan()
        self.assertEqual((result["items"][0]["amount"], result["items"][0]["observed_amount"], result["items"][0]["price_review"]), (20, 40, True))
        subscriptions.review(sub["id"], "accept_price")
        rescanned = subscriptions.scan()
        self.assertEqual((rescanned["items"][0]["amount"], rescanned["items"][0]["price_review"]), (40, False))


if __name__ == "__main__":
    unittest.main()
