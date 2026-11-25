"""Decision and persistence boundaries for conservative auto categorization."""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import db
import category_picker as picker


class CategoryPickerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.context = db.isolated_data(self.tmp.name)
        self.context.__enter__()
        db.init_db()
        db.ex("INSERT INTO accounts(id,name,scope,created_at) VALUES('personal','Personal','personal','2026-01-01')")
        db.ex("INSERT INTO accounts(id,name,scope,created_at) VALUES('business','Business','business','2026-01-01')")
        # The picker only needs allocation identity/active state, never receipt
        # content, provider credentials, or the receipt worker.
        db.ex("CREATE TABLE IF NOT EXISTS receipt_allocations (id TEXT, transaction_id TEXT, active INTEGER)")

    def tearDown(self):
        self.context.__exit__(None, None, None)
        self.tmp.cleanup()

    def tx(self, tid="new", **patches):
        return dict({"id": tid, "account_id": "personal", "scope": "personal", "amount": -12,
                     "name": "Local cafe", "merchant": "Local cafe", "category_id": None,
                     "posted": "2026-09-01", "created_at": "2026-09-01"}, **patches)

    def save(self, tx):
        keys = list(tx)
        db.ex("INSERT INTO transactions(" + ",".join(keys) + ") VALUES(" + ",".join("?" for _ in keys) + ")", [tx[k] for k in keys])
        return tx

    def custom(self, cid, name):
        db.ex("INSERT INTO categories(id,name,kind) VALUES(?,?,'expense')", (cid, name))

    def test_explicit_user_choice_trains_unknown_merchant_and_retains_custom_category(self):
        self.custom("my-food", "Eat out")
        self.save(self.tx("old", category_id="my-food", category_override=1))
        selected = picker.choose(self.tx())
        self.assertEqual(selected["category_id"], "my-food")
        self.assertEqual(selected["source"], "learned")
        self.assertIn("previous category", selected["reason"])

    def test_automatic_categories_do_not_train_other_transactions(self):
        self.save(self.tx("old", category_id="cat-dining", category_override=0))
        self.assertIsNone(picker.choose(self.tx()))

    def test_learning_respects_account_scope_even_with_stale_import_scope(self):
        self.save(self.tx("old", account_id="business", scope="personal", category_id="cat-biz-software", category_override=1))
        self.assertIsNone(picker.choose(self.tx()))
        business = picker.choose(self.tx(account_id="business", scope="personal"))
        self.assertEqual(business["category_id"], "cat-biz-software")

    def test_conflicting_manual_choices_prevent_a_merchant_default(self):
        self.save(self.tx("a", name="Starbucks", merchant="Starbucks", category_id="cat-dining", category_override=1))
        self.save(self.tx("b", name="Starbucks", merchant="Starbucks", category_id="cat-shopping", category_override=1))
        self.assertIsNone(picker.choose(self.tx(name="Starbucks", merchant="Starbucks")))

    def test_renamed_purchase_does_not_train_entire_merchant(self):
        self.save(self.tx("old", name="Invoice for office printer", merchant="Some Shop", name_override=1,
                          category_id="cat-biz-hardware", category_override=1))
        self.assertIsNone(picker.choose(self.tx(name="Some Shop", merchant="Some Shop")))

    def test_protected_financial_records_remain_untouched(self):
        for protection in (
            {"category_override": 1}, {"category_id": "cat-shopping"}, {"amount": 12},
            {"is_transfer": 1}, {"split_scope": "business"}, {"split_amount": 5},
            {"receipt_allocations": [{"category_id": "cat-shopping"}]},
            {"personal_finance_category": {"primary": "TRANSFER_OUT"}},
            {"personal_finance_category": {"primary": "LOAN_PAYMENTS"}},
        ):
            with self.subTest(protection=protection):
                self.assertIsNone(picker.choose(self.tx(merchant="Pirate Ship", **protection)))
        self.save(self.tx("itemized", merchant="Pirate Ship"))
        db.ex("INSERT INTO receipt_allocations(id,transaction_id,active) VALUES('r','itemized',1)")
        self.assertIsNone(picker.choose(self.tx("itemized", merchant="Pirate Ship")))

    def test_card_payment_is_not_classified_as_spending_from_merchant_name(self):
        self.assertIsNone(picker.choose(self.tx(name="MOBILE PAYMENT - THANK YOU", merchant="Pirate Ship")))

    def test_known_software_and_shipping_fix_common_unknowns(self):
        for merchant in ("Higgsfield Inc.", "Klingai", "Anthropic Headquarters", "Openrouter Inc", "Elevenlabs.io", "Cursor Ai Powered"):
            with self.subTest(merchant=merchant):
                picked = picker.choose(self.tx(merchant=merchant, account_id="business"))
                self.assertEqual(picked["category_id"], "cat-biz-software")
                self.assertEqual(picked["source"], "merchant")
        self.assertEqual(picker.choose(self.tx(merchant="Anthropic"))["category_id"], "cat-subscriptions")
        self.assertEqual(picker.choose(self.tx(merchant="Pirate Ship"))["category_id"], "cat-biz-shipping")

    def test_known_merchants_prefer_existing_copilot_category(self):
        self.custom("food", "Eat out")
        self.custom("gas", "Gas station")
        self.assertEqual(picker.choose(self.tx(merchant="Starbucks"))["category_id"], "food")
        self.assertEqual(picker.choose(self.tx(merchant="Chevron"))["category_id"], "gas")

    def test_mixed_merchants_are_not_guessed_from_one_prior_purchase(self):
        for index, merchant in enumerate(("Amazon", "Apple.com/bill", "PayPal", "Walmart", "Target", "Splitit")):
            with self.subTest(merchant=merchant):
                self.save(self.tx("old" + str(index), merchant=merchant, category_id="cat-biz-hardware", category_override=1))
                self.assertIsNone(picker.choose(self.tx(merchant=merchant)))

    def test_provider_detail_picks_specific_category_without_misusing_generic_merchandise(self):
        self.custom("parking", "Parking")
        picked = picker.choose(self.tx(personal_finance_category={"primary": "TRANSPORTATION", "detailed": "TRANSPORTATION_PARKING", "confidence_level": "HIGH"}))
        self.assertEqual(picked["category_id"], "parking")
        self.assertEqual(picked["source"], "bank")
        self.assertIsNone(picker.choose(self.tx(merchant="Amazon", personal_finance_category={"primary": "GENERAL_MERCHANDISE", "detailed": "GENERAL_MERCHANDISE_ONLINE_MARKETPLACES"})))
        self.assertIsNone(picker.choose(self.tx(personal_finance_category={"primary": "MEDICAL", "confidence_level": "LOW"})))

    def test_named_uncategorized_category_can_be_filled(self):
        self.custom("uncat", "Uncategorized")
        self.assertEqual(picker.choose(self.tx(merchant="Pirate Ship", category_id="uncat"))["category_id"], "cat-biz-shipping")

    def test_uses_callers_transaction_without_committing_or_mutating(self):
        conn = db._conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT INTO categories(id,name,kind) VALUES('newfood','Eat out','expense')")
            picked = picker.choose(self.tx(merchant="Starbucks"), conn=conn)
            self.assertEqual(picked["category_id"], "newfood")
            self.assertTrue(conn.in_transaction)
            conn.rollback()
            self.assertIsNone(db.q1("SELECT id FROM categories WHERE id='newfood'"))
        finally:
            conn.close()

    def test_backfill_previews_then_applies_once_with_reversible_audit(self):
        self.save(self.tx("software", merchant="Higgsfield Inc.", account_id="business", name="HIGGSFIELD INC.", name_override=1))
        self.save(self.tx("manual", merchant="Pirate Ship", category_override=1))
        self.save(self.tx("unknown", merchant="Unknown"))
        preview = picker.backfill()
        self.assertEqual(preview["suggestion_count"], 1)
        self.assertEqual(preview["changed_count"], 0)
        self.assertIsNone(db.q1("SELECT category_id FROM transactions WHERE id='software'")["category_id"])
        self.assertIsNone(db.q1("SELECT name FROM sqlite_master WHERE name='category_picker_audit'"))
        applied = picker.backfill(dry_run=False)
        self.assertEqual(applied["changed_count"], 1)
        self.assertEqual(db.q1("SELECT category_id FROM transactions WHERE id='software'")["category_id"], "cat-biz-software")
        self.assertEqual(picker.backfill(False)["changed_count"], 0)
        undone = picker.rollback(applied["run_id"])
        self.assertEqual(undone["restored_count"], 1)
        tx = db.q1("SELECT * FROM transactions WHERE id='software'")
        self.assertIsNone(tx["category_id"])
        self.assertEqual(tx["name"], "HIGGSFIELD INC.")
        self.assertEqual(tx["name_override"], 1)

    def test_rollback_cannot_overwrite_later_manual_category_or_receipt(self):
        self.save(self.tx("a", merchant="Pirate Ship"))
        self.save(self.tx("b", merchant="Pirate Ship"))
        run = picker.backfill(False)["run_id"]
        db.ex("UPDATE transactions SET category_id='cat-shopping',category_override=1 WHERE id='a'")
        db.ex("INSERT INTO receipt_allocations(id,transaction_id,active) VALUES('r','b',1)")
        result = picker.rollback(run)
        self.assertEqual(result["restored_count"], 0)
        self.assertEqual(result["skipped_count"], 2)
        self.assertEqual(db.q1("SELECT category_id FROM transactions WHERE id='a'")["category_id"], "cat-shopping")

    def test_failed_audit_rolls_back_transaction_changes(self):
        self.save(self.tx("a", merchant="Pirate Ship"))
        with patch.object(picker, "init_schema", side_effect=RuntimeError("test failure")):
            with self.assertRaises(RuntimeError):
                picker.backfill(False)
        self.assertIsNone(db.q1("SELECT category_id FROM transactions WHERE id='a'")["category_id"])


if __name__ == "__main__":
    unittest.main()
