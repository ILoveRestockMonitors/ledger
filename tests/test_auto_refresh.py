"""Automatic Plaid re-check for stale connections, limited to once a day."""
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
import scheduler


def ago(**kw):
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(**kw)).isoformat().replace("+00:00", "Z")


class AutoRefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.context = db.isolated_data(self.tmp.name)
        self.context.__enter__()
        db.init_db()

    def tearDown(self):
        self.context.__exit__(None, None, None)
        self.tmp.cleanup()

    def item(self, seen, archived=0, asked=None):
        db.ex("INSERT INTO items(id,institution,env,access_token,created_at,bank_updated_at,bank_refresh_requested_at) VALUES('i','Bank','production','tok','2026-01-01',?,?)", (seen, asked))
        db.ex("INSERT INTO accounts(id,item_id,name,scope,archived,created_at) VALUES('a','i','A','personal',?,'2026-01-01')", (archived,))

    def calls(self):
        with patch.object(p, "_post", return_value={}) as post:
            result = p.request_refresh_if_stale("i")
        return result, [c[0][0] for c in post.call_args_list]

    def test_stale_connection_is_refreshed_once_a_day(self):
        self.item(ago(days=5))
        self.assertEqual(self.calls(), (True, ["/transactions/refresh"]))
        self.assertEqual(self.calls(), (False, []))

    def test_allowed_again_after_a_day(self):
        self.item(ago(days=5), asked=ago(hours=25))
        self.assertEqual(self.calls(), (True, ["/transactions/refresh"]))

    def test_current_unknown_or_archived_are_left_alone(self):
        self.item(ago(hours=2))
        self.assertEqual(self.calls(), (False, []))
        db.ex("UPDATE items SET bank_updated_at=NULL")
        self.assertEqual(self.calls(), (False, []))
        db.ex("UPDATE items SET bank_updated_at=?", (ago(days=5),))
        db.ex("UPDATE accounts SET archived=1")
        self.assertEqual(self.calls(), (False, []))

    def test_refused_call_is_recorded_and_not_repeated(self):
        self.item(ago(days=5))
        with patch.object(p, "_post", side_effect=p.PlaidError("no")):
            with self.assertRaises(p.PlaidError):
                p.request_refresh_if_stale("i")
        self.assertEqual(self.calls(), (False, []))

    def test_refused_call_does_not_fail_the_sync(self):
        self.item(ago(days=5))
        with patch.object(scheduler, "_test_mode", return_value=False), \
                patch.object(p, "refresh_item", return_value={"added": 0}), \
                patch.object(p, "request_refresh_if_stale", side_effect=p.PlaidError("no")), \
                patch("subscriptions.scan", return_value={}):
            outcome = scheduler.sync_all()
        self.assertEqual([r["status"] for r in outcome["items"]], ["ok"])


if __name__ == "__main__":
    unittest.main()
