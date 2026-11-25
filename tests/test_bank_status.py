"""Reconnect behavior for healthy and out-of-date bank connections."""
import datetime
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import db
import plaid_client as p


def ago(days):
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).isoformat().replace("+00:00", "Z")


class BankStatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.context = db.isolated_data(self.tmp.name)
        self.context.__enter__()
        db.init_db()

    def tearDown(self):
        self.context.__exit__(None, None, None)
        self.tmp.cleanup()

    def item(self, seen):
        db.ex("INSERT INTO items(id,institution,env,access_token,created_at,bank_updated_at) VALUES('i','Bank','production','tok','2026-01-01',?)", (seen,))

    def link_payload(self):
        with patch.object(p, "_post", return_value={"link_token": "x"}) as post:
            p.create_link_token(item_id="i")
        return post.call_args[0][1]

    def test_out_of_date_connection_asks_for_full_screens(self):
        self.item(ago(12))
        self.assertEqual(self.link_payload()["update"], {"account_selection_enabled": True})

    def test_current_or_unknown_connection_keeps_normal_flow(self):
        self.item(ago(1))
        self.assertNotIn("update", self.link_payload())
        db.ex("UPDATE items SET bank_updated_at=NULL WHERE id='i'")
        self.assertNotIn("update", self.link_payload())

    def test_status_is_stored_and_failure_never_breaks_a_sync(self):
        self.item(None)
        row = dict(db.q1("SELECT * FROM items WHERE id='i'"))
        with patch.object(p, "_post", return_value={"status": {"transactions": {"last_successful_update": "2026-10-23T10:00:00Z"}}}):
            self.assertEqual(p._record_bank_status(row), "2026-10-23T10:00:00Z")
        self.assertEqual(db.q1("SELECT bank_updated_at b FROM items WHERE id='i'")["b"], "2026-10-23T10:00:00Z")
        row["bank_updated_at"] = "kept"
        with patch.object(p, "_post", side_effect=p.PlaidError("down")):
            self.assertEqual(p._record_bank_status(row), "kept")


if __name__ == "__main__":
    unittest.main()
