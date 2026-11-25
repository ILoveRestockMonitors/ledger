"""An account can follow the bank's available balance without affecting others."""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import db
import plaid_client as p


class BalanceSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.context = db.isolated_data(self.tmp.name)
        self.context.__enter__()
        db.init_db()
        db.ex("INSERT INTO items(id,institution,env,access_token,created_at) VALUES('i','Bank','production','tok','2026-01-01')")
        for local, plaid, source in (("avail", "pa", "available"), ("curr", "pc", None)):
            db.ex("INSERT INTO accounts(id,item_id,name,type,scope,mask,balance,plaid_account_id,balance_source,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                  (local, "i", local, "depository", "business", plaid, 1, plaid, source, "2026-01-01"))

    def tearDown(self):
        self.context.__exit__(None, None, None)
        self.tmp.cleanup()

    def account(self, plaid, current, available):
        return {"account_id": plaid, "type": "depository", "mask": plaid, "balances": {"current": current, "available": available}}

    def sync(self, accounts):
        with patch.object(p, "sync_transactions", return_value={"added": [], "modified": [], "removed": [], "cursor": "c"}), \
                patch.object(p, "fetch_accounts", return_value={"item": {}, "accounts": accounts}), \
                patch.object(p, "_post", return_value={}):
            p.refresh_item("i")
        return {r["id"]: r["balance"] for r in db.q("SELECT id,balance FROM accounts")}

    def test_only_the_chosen_account_uses_available(self):
        saved = self.sync([self.account("pa", 332.81, 399.48), self.account("pc", 10, 20)])
        self.assertEqual(saved, {"avail": 399.48, "curr": 10})

    def test_missing_available_falls_back_to_current(self):
        saved = self.sync([self.account("pa", 332.81, None), self.account("pc", 10, 20)])
        self.assertEqual(saved["avail"], 332.81)

    def test_zero_available_is_respected(self):
        self.assertEqual(p._balance(self.account("pa", 50, 0), "available"), 0)

    def test_default_and_credit_are_unchanged(self):
        self.assertEqual(p._balance(self.account("pa", 50, 70)), 50)
        self.assertEqual(p._balance({"type": "credit", "balances": {"current": 50, "available": 70}}), -50)


if __name__ == "__main__":
    unittest.main()
