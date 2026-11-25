"""Bank-category trust, merchant rules, recency and the suggestion-only model."""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import db
import category_picker as picker


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.context = db.isolated_data(self.tmp.name)
        self.context.__enter__()
        db.init_db()
        db.ex("INSERT INTO accounts(id,name,scope,created_at) VALUES('p','Personal','personal','2026-01-01')")
        db.ex("CREATE TABLE IF NOT EXISTS receipt_allocations (id TEXT, transaction_id TEXT, active INTEGER)")
        db.ex("INSERT OR IGNORE INTO categories(id,name,kind) VALUES('cat-gas','Gas station','expense')")
        self.n = 0

    def tearDown(self):
        self.context.__exit__(None, None, None)
        self.tmp.cleanup()

    def cat(self, name):
        return db.q1("SELECT id FROM categories WHERE name=?", (name,))["id"]

    def add(self, merchant, category=None, override=0, posted="2026-01-01", **extra):
        self.n += 1
        tid = "t%d" % self.n
        db.ex("INSERT INTO transactions(id,account_id,scope,amount,posted,name,merchant,category_id,category_override,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
              (tid, "p", "personal", -10, posted, merchant, merchant, category, override, "2026-01-01"))
        for key, value in extra.items():
            db.ex("UPDATE transactions SET %s=? WHERE id=?" % key, (value, tid))
        return tid

    def pick(self, merchant, detailed="", primary="", confidence=""):
        return picker.choose({"id": "new", "account_id": "p", "scope": "personal", "amount": -10, "name": merchant, "merchant": merchant,
                              "personal_finance_category": {"primary": primary, "detailed": detailed, "confidence_level": confidence}})


class BankCategoryTests(Base):
    def test_medium_bank_category_is_used(self):
        result = self.pick("Corner Stop", "TRANSPORTATION_GAS", "TRANSPORTATION", "MEDIUM")
        self.assertEqual(result["category_id"], self.cat("Gas station"))
        self.assertEqual(result["source"], "bank")

    def test_low_bank_category_is_ignored(self):
        self.assertIsNone(self.pick("Corner Stop", "TRANSPORTATION_GAS", "TRANSPORTATION", "LOW"))

    def test_generic_other_code_needs_very_high_confidence(self):
        self.assertIsNone(self.pick("Some App", "ENTERTAINMENT_OTHER_ENTERTAINMENT", "ENTERTAINMENT", "HIGH"))
        self.assertIsNotNone(self.pick("Some App", "ENTERTAINMENT_OTHER_ENTERTAINMENT", "ENTERTAINMENT", "VERY_HIGH"))

    def test_mixed_retailer_ignores_medium_bank_category(self):
        self.assertIsNone(self.pick("Walmart", "FOOD_AND_DRINK_GROCERIES", "FOOD_AND_DRINK", "MEDIUM"))

    def test_stored_bank_category_reaches_backfill(self):
        tid = self.add("Corner Stop", bank_category_primary="TRANSPORTATION", bank_category_detailed="TRANSPORTATION_GAS", bank_category_confidence="HIGH")
        result = picker.backfill(dry_run=True)
        self.assertEqual([c["transaction_id"] for c in result["candidates"]], [tid])

    def test_stored_transfer_code_protects_a_row(self):
        self.add("Corner Stop", bank_category_primary="TRANSFER_OUT", bank_category_detailed="TRANSPORTATION_GAS", bank_category_confidence="HIGH")
        self.assertEqual(picker.backfill(dry_run=True)["suggestion_count"], 0)


class MerchantRuleTests(Base):
    def test_named_merchants(self):
        self.assertEqual(self.pick("Aromas")["category_id"], self.cat("Gas station"))
        self.assertEqual(self.pick("The Local Shoppe")["category_id"], self.cat("Groceries"))
        self.assertEqual(self.pick("DEBIT CARD PURCHASE DT PAY BY SPACE - 0100")["source"], "merchant")
        self.assertEqual(self.pick("SQSP* INV190544848")["source"], "merchant")
        self.assertEqual(self.pick("In-shape")["source"], "merchant")

    def test_mixed_retailers_stay_unassigned(self):
        for name in ("Amazon", "Walmart", "Target", "Venmo", "Zelle"):
            self.assertIsNone(self.pick(name), name)


class HistoryTests(Base):
    def test_one_past_choice_yields_to_clear_bank_category(self):
        self.add("Corner Stop", self.cat("Shopping"), 1)
        result = self.pick("Corner Stop", "TRANSPORTATION_GAS", "TRANSPORTATION", "HIGH")
        self.assertEqual(result["category_id"], self.cat("Gas station"))

    def test_one_past_choice_beats_medium_bank_category(self):
        self.add("Corner Stop", self.cat("Shopping"), 1)
        result = self.pick("Corner Stop", "TRANSPORTATION_GAS", "TRANSPORTATION", "MEDIUM")
        self.assertEqual(result["category_id"], self.cat("Shopping"))

    def test_two_matching_choices_beat_bank_category(self):
        self.add("Corner Stop", self.cat("Shopping"), 1)
        self.add("Corner Stop", self.cat("Shopping"), 1)
        result = self.pick("Corner Stop", "TRANSPORTATION_GAS", "TRANSPORTATION", "HIGH")
        self.assertEqual(result["category_id"], self.cat("Shopping"))

    def test_conflicting_choices_defer_to_clear_bank_category_only(self):
        self.add("Corner Stop", self.cat("Shopping"), 1)
        self.add("Corner Stop", self.cat("Groceries"), 1)
        self.assertEqual(self.pick("Corner Stop", "TRANSPORTATION_GAS", "TRANSPORTATION", "HIGH")["source"], "bank")
        self.assertIsNone(self.pick("Corner Stop", "TRANSPORTATION_GAS", "TRANSPORTATION", "MEDIUM"))
        self.assertIsNone(self.pick("Corner Stop"))

    def test_only_recent_choices_count(self):
        self.add("Corner Stop", self.cat("Shopping"), 1, posted="2020-01-01")
        for day in range(1, 6):
            self.add("Corner Stop", self.cat("Groceries"), 1, posted="2026-01-0%d" % day)
        self.assertEqual(self.pick("Corner Stop")["category_id"], self.cat("Groceries"))


class BackfillTests(Base):
    def test_sources_limit_what_is_applied_and_manual_rows_stay(self):
        manual = self.add("Aromas", self.cat("Groceries"), 1)
        rule = self.add("Aromas Two")
        self.add("Oak Cafe", self.cat("Shopping"), 1)
        learned = self.add("Oak Cafe")
        result = picker.backfill(dry_run=False, sources=("merchant", "bank", "rule"))
        self.assertEqual({c["transaction_id"] for c in result["candidates"]}, {rule})
        self.assertEqual(db.q1("SELECT category_id c FROM transactions WHERE id=?", (manual,))["c"], self.cat("Groceries"))
        self.assertIsNone(db.q1("SELECT category_id c FROM transactions WHERE id=?", (learned,))["c"])
        picker.rollback(result["run_id"])
        self.assertIsNone(db.q1("SELECT category_id c FROM transactions WHERE id=?", (rule,))["c"])


class ModelTests(Base):
    def seed(self):
        for _ in range(4):
            self.add("Oak Harbor Cafe", self.cat("Groceries"), 1)
            self.add("Pine Tree Hardware", self.cat("Shopping"), 1)

    def test_suggests_without_writing(self):
        import category_model
        self.seed()
        tid = self.add("Oak Harbor Cafe Downtown")
        before = dict(db.q1("SELECT category_id c, category_override o FROM transactions WHERE id=?", (tid,)))
        result = category_model.suggest(tid)
        self.assertTrue(result)
        self.assertEqual(result[0]["category_id"], self.cat("Groceries"))
        self.assertEqual(dict(db.q1("SELECT category_id c, category_override o FROM transactions WHERE id=?", (tid,))), before)

    def test_no_suggestion_for_assigned_mixed_or_unknown(self):
        import category_model
        self.seed()
        self.assertEqual(category_model.suggest(self.add("Oak Harbor Cafe", self.cat("Shopping"))), [])
        self.assertEqual(category_model.suggest(self.add("Amazon Oak Harbor")), [])
        self.assertEqual(category_model.suggest(self.add("Zzyzx Qqq")), [])
        self.assertEqual(category_model.suggest("missing"), [])


if __name__ == "__main__":
    unittest.main()
