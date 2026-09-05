import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import db
import receipt_store
import reports


class ReceiptStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = db.DATA_DIR, db.DB_PATH, db.CONFIG_PATH
        db.DATA_DIR = self.tmp.name
        db.DB_PATH = os.path.join(self.tmp.name, "ledger.db")
        db.CONFIG_PATH = os.path.join(self.tmp.name, "config.json")
        db.init_db()
        receipt_store.init_schema()
        db.ex("INSERT INTO accounts(id,name,scope,balance,iso_currency,mask,created_at) VALUES(?,?,?,?,?,?,?)", ("a", "Checking", "personal", 0, "USD", "1234", "2026-01-01"))
        db.ex("INSERT INTO transactions(id,account_id,scope,amount,posted,name,merchant,created_at) VALUES(?,?,?,?,?,?,?,?)", ("t", "a", "personal", -12.34, "2026-09-01", "AMZN Mktplace", "AMAZON", "2026-09-01"))

    def tearDown(self):
        db.DATA_DIR, db.DB_PATH, db.CONFIG_PATH = self.old
        self.tmp.cleanup()

    def _payload(self, order="order-1", amount=1234, confidence=.95):
        return {"status": "matched", "proposal": {
            "description": "Amazon order", "match_confidence": confidence,
            "receipt": {"url": "https://example.test/receipt/" + order, "order_id": order, "purchased_on": "2026-09-01", "currency": "USD", "total_cents": amount, "card_last4": "1234"},
            "items": [{"description": "Toothbrush", "amount_cents": amount, "category_id": "cat-personal-care", "confidence": .95}],
        }}

    def test_verified_exact_receipt_applies_allocations_and_reports_parent_once(self):
        job = receipt_store.request("t")
        claimed = receipt_store.claim_next()
        self.assertEqual(claimed["transaction"]["mask"], "1234")
        result = receipt_store.finish(job["id"], self._payload(), verified=True)
        self.assertEqual(result["status"], "applied")
        self.assertEqual(receipt_store.allocation_map(["t"])["t"][0]["amount_cents"], 1234)
        self.assertEqual(reports.spending_report(2026, as_of="2026-09-15")["year_total"], 12.34)
        decorated = receipt_store.decorate_transactions([db.q1("SELECT * FROM transactions WHERE id='t'")])[0]
        self.assertEqual((decorated["display_name"], decorated["receipt_status"], decorated["allocations"][0]["cat_name"]), ("Amazon order", "applied", "Personal Care"))

    def test_unverified_proposal_cannot_be_manually_accepted(self):
        job = receipt_store.request("t")
        receipt_store.claim_next()
        receipt_store.finish(job["id"], self._payload(), verified=False)
        with self.assertRaises(ValueError):
            receipt_store.review(job["id"], "accept")
        self.assertEqual(receipt_store.detail("t")["allocations"], [])

    def test_fingerprint_change_invalidates_allocations_fail_closed(self):
        job = receipt_store.request("t")
        receipt_store.claim_next()
        receipt_store.finish(job["id"], self._payload(), verified=True)
        db.ex("UPDATE transactions SET amount=-13.34 WHERE id='t'")
        self.assertEqual(receipt_store.allocation_map(["t"]), {})
        self.assertIsNone(receipt_store.decorate_transactions([db.q1("SELECT * FROM transactions WHERE id='t'")])[0]["receipt_status"])
        self.assertEqual(receipt_store.invalidate_transaction("t"), True)
        self.assertEqual(receipt_store.detail("t")["job"]["status"], "review")

    def test_mismatched_allocation_is_rejected_and_duplicate_order_is_not_applied(self):
        job = receipt_store.request("t")
        receipt_store.claim_next()
        bad = self._payload(amount=1233)
        with self.assertRaises(ValueError):
            receipt_store.finish(job["id"], bad, verified=True)

        good = self._payload()
        receipt_store.finish(job["id"], good, verified=True)
        db.ex("INSERT INTO transactions(id,account_id,scope,amount,posted,name,merchant,created_at) VALUES(?,?,?,?,?,?,?,?)", ("t2", "a", "personal", -12.34, "2026-09-02", "AMZN Mktplace", "AMAZON", "2026-09-02"))
        job2 = receipt_store.request("t2")
        receipt_store.claim_next()
        result = receipt_store.finish(job2["id"], good, verified=True)
        self.assertEqual(result["status"], "needs_user")
        self.assertEqual(receipt_store.allocation_map(["t2"]), {})

    def test_review_can_correct_each_item_category_without_changing_amounts(self):
        payload = self._payload(confidence=.5)
        payload["proposal"]["items"][0]["category_id"] = None
        job = receipt_store.request("t")
        receipt_store.claim_next()
        result = receipt_store.finish(job["id"], payload, verified=True)
        self.assertEqual(result["status"], "review")
        applied = receipt_store.review(job["id"], "accept", ["cat-personal-care"])
        self.assertEqual(applied["status"], "applied")
        allocation = receipt_store.detail("t")["allocations"][0]
        self.assertEqual((allocation["amount_cents"], allocation["category_id"], allocation["manual_category"]), (1234, "cat-personal-care", 1))

    def test_daily_attempt_limit_covers_resume_and_missing_mask_stays_review(self):
        db.save_config({"receipt_daily_limit": 1})
        job = receipt_store.request("t")
        receipt_store.claim_next()
        receipt_store.finish(job["id"], {"status": "failed", "message": "retry"})
        receipt_store.resume(job["id"])
        self.assertIsNone(receipt_store.claim_next())

        db.save_config({"receipt_daily_limit": 10})
        db.ex("UPDATE accounts SET mask=NULL WHERE id='a'")
        job2 = receipt_store.request("t")
        receipt_store.claim_next()
        result = receipt_store.finish(job2["id"], self._payload(order="order-mask"), verified=True)
        self.assertEqual((result["status"], result["can_apply"]), ("review", True))

    def test_claim_rechecks_archived_account_and_expected_attempt_blocks_stale_worker(self):
        job = receipt_store.request("t")
        first = receipt_store.claim_next()
        self.assertEqual(first["attempts"], 1)
        db.ex("UPDATE receipt_jobs SET updated_at=? WHERE id=?", ("2000-01-01T00:00:00", job["id"]))
        second = receipt_store.claim_next()
        self.assertEqual(second["attempts"], 2)
        with self.assertRaises(ValueError):
            receipt_store.finish(job["id"], self._payload(order="stale"), verified=True, expected_attempt=1)
        self.assertEqual(receipt_store.finish(job["id"], self._payload(order="fresh"), verified=True, expected_attempt=2)["status"], "applied")

        db.ex("INSERT INTO transactions(id,account_id,scope,amount,posted,name,merchant,created_at) VALUES(?,?,?,?,?,?,?,?)", ("t2", "a", "personal", -5, "2026-09-02", "Amazon", "AMAZON", "2026-09-02"))
        job2 = receipt_store.request("t2")
        db.ex("UPDATE accounts SET archived=1 WHERE id='a'")
        self.assertIsNone(receipt_store.claim_next())
        self.assertEqual(db.q1("SELECT status FROM receipt_jobs WHERE id=?", (job2["id"],))["status"], "failed")

    def test_malformed_worker_payload_is_rejected_before_claim_can_apply(self):
        job = receipt_store.request("t")
        receipt_store.claim_next()
        malformed = self._payload(order="bad")
        malformed["message"] = "x" * 5000
        malformed["proposal"]["receipt"] = "not-an-object"
        with self.assertRaises(ValueError):
            receipt_store.finish(job["id"], malformed, verified=True)
        self.assertEqual(db.q1("SELECT status FROM receipt_jobs WHERE id=?", (job["id"],))["status"], "running")

        malformed = self._payload(order="bad-confidence")
        malformed["proposal"]["items"][0]["confidence"] = float("inf")
        with self.assertRaises(ValueError):
            receipt_store.finish(job["id"], malformed, verified=True)


if __name__ == "__main__":
    unittest.main()
