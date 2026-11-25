"""2026-11-07: low-confidence food goes to Eat out; town-only merchants get the store name."""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import db
import category_picker as picker
import tx_names


class Names(unittest.TestCase):
    def test_town_only_merchant_uses_store(self):
        raw = "DEBIT CARD PURCHASE AT CAPITOLA GROCER, CAPITOLA, CA ON 110626 FROM CARD#: XXXXXXXXXXXX4071"
        self.assertEqual(tx_names.clean_merchant(raw, "Capitola"), "Capitola Grocer")

    def test_good_plaid_names_are_kept(self):
        self.assertEqual(tx_names.clean_merchant("DEBIT CARD PURCHASE EBAY US - 001 7700 EASTPORT", "eBay"), "eBay")
        self.assertEqual(tx_names.clean_merchant("CARD TRANSACTION : GREY BEARS, Santa Cruz, CA FROM CARD#: X", "Grey Bears"), "Grey Bears")
        self.assertEqual(tx_names.clean_merchant("Goodwill", "Goodwill"), "Goodwill")
        self.assertEqual(tx_names.clean_merchant("ACH DEBIT RENT", ""), "ACH DEBIT RENT")


class Food(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.context = db.isolated_data(self.tmp.name)
        self.context.__enter__()
        db.init_db()
        db.ex("INSERT INTO accounts(id,name,scope,created_at) VALUES('p','Personal','personal','2026-01-01')")
        db.ex("CREATE TABLE IF NOT EXISTS receipt_allocations (id TEXT, transaction_id TEXT, active INTEGER)")

    def tearDown(self):
        self.context.__exit__(None, None, None)
        self.tmp.cleanup()

    def name(self, tx):
        got = picker.choose(dict({"amount": -10, "account_id": "p", "scope": "personal"}, **tx))
        return got and db.q1("SELECT name FROM categories WHERE id=?", (got["category_id"],))["name"]

    def test_low_confidence_grocery_is_eat_out(self):
        self.assertIn(self.name({"name": "x", "merchant": "Capitola Grocer", "personal_finance_category": {"primary": "FOOD_AND_DRINK", "detailed": "FOOD_AND_DRINK_GROCERIES", "confidence_level": "LOW"}}), ("Eat out", "Dining & Coffee"))

    def test_confident_grocery_stays_groceries(self):
        self.assertEqual(self.name({"name": "x", "merchant": "Sigona's", "personal_finance_category": {"primary": "FOOD_AND_DRINK", "detailed": "FOOD_AND_DRINK_GROCERIES", "confidence_level": "MEDIUM"}}), "Groceries")

    def test_low_vending_and_low_non_food_stay_blank(self):
        self.assertIsNone(self.name({"name": "x", "merchant": "Vendoo", "personal_finance_category": {"primary": "FOOD_AND_DRINK", "detailed": "FOOD_AND_DRINK_VENDING_MACHINES", "confidence_level": "LOW"}}))
        self.assertIsNone(self.name({"name": "x", "merchant": "Shop", "personal_finance_category": {"primary": "GENERAL_MERCHANDISE", "detailed": "GENERAL_MERCHANDISE_CONVENIENCE_STORES", "confidence_level": "LOW"}}))

    def test_convenience_store_is_eat_out(self):
        self.assertIn(self.name({"name": "x", "merchant": "Circle K", "personal_finance_category": {"primary": "GENERAL_MERCHANDISE", "detailed": "GENERAL_MERCHANDISE_CONVENIENCE_STORES", "confidence_level": "HIGH"}}), ("Eat out", "Dining & Coffee"))

    def test_low_food_never_beats_manual_history(self):
        db.ex("INSERT INTO transactions(id,account_id,scope,amount,posted,name,merchant,category_id,category_override,created_at) VALUES('h','p','personal',-40,'2026-01-01','BOFBOT','Bofbot','cat-biz-software',1,'2026-01-01')")
        self.assertEqual(self.name({"name": "BOFBOT", "merchant": "Bofbot", "personal_finance_category": {"primary": "FOOD_AND_DRINK", "detailed": "FOOD_AND_DRINK_GROCERIES", "confidence_level": "LOW"}}), "Software & SaaS")


if __name__ == "__main__":
    unittest.main()


class Familiar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.context = db.isolated_data(self.tmp.name)
        self.context.__enter__()
        db.init_db()
        db.ex("INSERT INTO accounts(id,name,scope,created_at) VALUES('p','Personal','personal','2026-01-01')")
        db.ex("CREATE TABLE IF NOT EXISTS receipt_allocations (id TEXT, transaction_id TEXT, active INTEGER)")
        self.n = 0

    def tearDown(self):
        self.context.__exit__(None, None, None)
        self.tmp.cleanup()

    def add(self, name, merchant, category=None, override=0, scope="personal"):
        self.n += 1
        tid = "t%d" % self.n
        db.ex("INSERT INTO transactions(id,account_id,scope,amount,posted,name,merchant,category_id,category_override,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
              (tid, "p", scope, -10, "2026-01-%02d" % self.n, name, merchant, category, override, "2026-01-01"))
        return tid

    def test_same_store_other_spelling_is_familiar(self):
        self.add("Grocery Outlet", "Grocery Outlet", "cat-dining", 1)
        got = picker.choose({"amount": -5, "account_id": "p", "scope": "personal",
                             "name": "Grocery Outlet Of Sasanta Barbara", "merchant": "Grocery Outlet Of Sasanta Barbara"})
        self.assertEqual(got["category_id"], "cat-dining")
        self.assertIn("store", got["reason"])

    def test_shared_town_word_is_not_same_store(self):
        self.assertFalse(tx_names.same_store("santa cruz cinema", "santa cruz groc"))
        self.assertFalse(tx_names.same_store("market", "market place"))
        self.assertTrue(tx_names.same_store("pacific cookie", "pacific cookie co"))

    def test_remember_renames_past_and_future(self):
        first = self.add("DEBIT CARD PURCHASE AT CAPITOLA GROCER, CAPITOLA, CA", "Capitola Grocer")
        second = self.add("DEBIT CARD PURCHASE AT CAPITOLA GROCER, CAPITOLA, CA", "Capitola Grocer")
        other = self.add("Safeway", "Safeway")
        c = db._conn()
        self.assertEqual(tx_names.remember(c, first, "Grocery Outlet"), 2)
        c.commit()
        rows = {r["id"]: r for r in c.execute("SELECT * FROM transactions")}
        self.assertEqual(rows[second]["merchant"], "Grocery Outlet")
        self.assertEqual(rows[second]["bank_merchant"], "Capitola Grocer")
        self.assertEqual(rows[other]["merchant"], "Safeway")
        # A new bank row from the same store gets the taught name; renaming again keeps the bank key.
        raw = "DEBIT CARD PURCHASE AT CAPITOLA GROCER, CAPITOLA, CA ON 110626 FROM CARD#: X"
        self.assertEqual(tx_names.display_merchant(raw, "Capitola", tx_names.aliases(c)), "Grocery Outlet")
        self.assertEqual(tx_names.remember(c, second, "Grocery Outlet Capitola"), 2)
        c.close()


class Thrift(Food):
    def test_thrift_is_shopping_on_any_card(self):
        db.ex("INSERT INTO accounts(id,name,scope,created_at) VALUES('b','Biz','business','2026-01-01')")
        for merchant in ("Grey Bears", "Goodwill Central Coast", "Savers"):
            got = picker.choose({"amount": -10, "account_id": "b", "scope": "business", "name": merchant, "merchant": merchant})
            self.assertEqual(db.q1("SELECT name FROM categories WHERE id=?", (got["category_id"],))["name"], "Shopping")
