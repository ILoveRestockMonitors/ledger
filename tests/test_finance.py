import os
import sys
import tempfile
import unittest
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "backend"))


class FinanceTests(unittest.TestCase):
    def setUp(self):
        import db
        self.tmp = tempfile.TemporaryDirectory()
        db.DB_PATH = os.path.join(self.tmp.name, "ledger.db")
        db.DATA_DIR = self.tmp.name
        db.init_db()
        import subscriptions
        subscriptions.init_schema()
        self.db = db
        self.subscriptions = subscriptions
        self.forecasts = __import__("forecasts")
        self.analytics = __import__("analytics")
        self._add_account()

    def tearDown(self): self.tmp.cleanup()

    def _add_account(self):
        self.db.ex("INSERT INTO accounts(id,name,scope,balance,created_at) VALUES(?,?,?,?,?)", ("a", "Checking", "personal", 0, "2026-01-01"))

    def _tx(self, merchant, when, amount=12):
        self.db.ex("INSERT INTO transactions(id,account_id,scope,amount,posted,name,merchant,created_at) VALUES(?,?,?,?,?,?,?,?)", ("t" + when.replace("-", ""), "a", "personal", -amount, when, merchant, merchant, when))

    def _pending_tx(self, merchant, when, amount=12):
        self.db.ex("INSERT INTO transactions(id,account_id,scope,amount,posted,name,merchant,pending,created_at) VALUES(?,?,?,?,?,?,?,?,?)", ("p" + when.replace("-", ""), "a", "personal", -amount, when, merchant, merchant, 1, when))

    def test_scan_is_idempotent_and_detects_early_candidate(self):
        for d in (date(2026, 1, 5), date(2026, 2, 5)):
            self._tx("Warm Cloud", d.isoformat())
        one = self.subscriptions.scan(); two = self.subscriptions.scan()
        self.assertEqual(len(one["candidates"]), 1)
        self.assertEqual(len(self.db.q("SELECT * FROM subscriptions")), 1)
        self.assertEqual(len(two["candidates"]), 1)

    def test_dismissal_is_remembered(self):
        self._tx("Maybe", "2026-01-01"); self._tx("Maybe", "2026-02-01")
        sub = self.subscriptions.scan()["candidates"][0]
        self.subscriptions.review(sub["id"], "dismiss")
        self.assertEqual(self.subscriptions.scan()["candidates"], [])

    def test_annual_cadence_and_monthly_equivalent(self):
        self._tx("Renewal", "2025-01-15", 120); self._tx("Renewal", "2026-01-15", 132)
        sub = self.subscriptions.scan()["candidates"][0]
        self.assertEqual(sub["cadence"], "annual")
        self.assertEqual(sub["monthly_equivalent"], 11.0)

    def test_monthly_billing_anchor_survives_short_february(self):
        jan = date(2026, 1, 31)
        feb = self.subscriptions._add_due(jan, "monthly", anchor_day=31)
        mar = self.subscriptions._add_due(feb, "monthly", anchor_day=31)
        self.assertEqual(feb, date(2026, 2, 28))
        self.assertEqual(mar, date(2026, 3, 31))

    def test_plan_does_not_double_count_posted_subscription(self):
        self._tx("Cloud", "2026-09-01", 20); self.subscriptions.save({"merchant":"Cloud","scope":"personal","account_id":"a","amount":20,"cadence":"monthly","next_due":"2026-09-01","status":"active"})
        plan = self.subscriptions.monthly_plan("personal", "2026-09")
        self.assertEqual(plan["spent"], 20)
        self.assertEqual(plan["upcoming"], 0)

    def test_pending_subscription_is_expected_once(self):
        self._pending_tx("Pending Cloud", "2026-09-05", 20)
        self.subscriptions.save({"merchant":"Pending Cloud","scope":"personal","account_id":"a","amount":20,"cadence":"monthly","next_due":"2026-09-05","status":"active"})
        plan = self.subscriptions.monthly_plan("personal", "2026-09")
        self.assertEqual(plan["spent"], 0)
        self.assertEqual(plan["upcoming"], 0)
        self.assertEqual(plan["total_expected"], 20)

    def test_forecast_compounds_and_rejects_bad_math(self):
        result = self.forecasts.project({"years": 2, "starting_investments": 1000, "monthly_investment": 100, "annual_return": 12})
        self.assertGreater(result["summary"]["base"], result["summary"]["conservative"])
        with self.assertRaises(ValueError): self.forecasts.project({"years": 2, "annual_return": float("nan")})

    def test_forecast_uses_effective_annual_return_exactly(self):
        row = self.forecasts.project({"years": 1, "starting_investments": 1000, "annual_return": 12})["series"][0]
        self.assertEqual((row["conservative"], row["base"], row["optimistic"]), (1090.0, 1120.0, 1150.0))

    def test_forecast_cash_savings_is_independent_and_exact(self):
        result = self.forecasts.project({"years": 1, "starting_cash": 100, "monthly_savings": 10, "monthly_investment": 25, "monthly_debt_payment": 5, "annual_return": 0})
        self.assertEqual(result["series"][0]["cash"], 220.0)
        self.assertEqual(result["series"][0]["investments"], 300.0)
        self.assertEqual(result["series"][0]["contributions"], 420.0)

    def test_defaults_derive_cash_investments_and_debt(self):
        self.db.ex("INSERT INTO accounts(id,name,type,scope,balance,created_at) VALUES(?,?,?,?,?,?)", ("inv", "Brokerage", "investment", "personal", 2500, "2026-01-01"))
        self.db.ex("INSERT INTO accounts(id,name,type,scope,balance,created_at) VALUES(?,?,?,?,?,?)", ("loan", "Card", "credit", "personal", -700, "2026-01-01"))
        d = self.forecasts.defaults("personal")
        self.assertEqual((d["starting_cash"], d["starting_investments"], d["starting_debt"]), (0.0, 2500.0, 700.0))

    def test_custom_cadence_and_account_validation(self):
        with self.assertRaises(ValueError): self.subscriptions.save({"merchant": "x", "scope": "personal", "account_id": "missing", "amount": 2, "cadence": "monthly"})
        with self.assertRaises(ValueError): self.subscriptions.save({"merchant": "x", "scope": "personal", "account_id": "a", "amount": 2, "cadence": "custom"})
        with self.assertRaises(ValueError): self.subscriptions.save({"merchant": "x", "scope": "personal", "account_id": "a", "amount": 2, "cadence": "monthly", "management_url": "http://bad"})

    def test_scan_ignores_pending_future_and_stale_autoactivation(self):
        self._pending_tx("Netflix", "2026-08-01", 18)
        self._pending_tx("Netflix", "2026-09-01", 18)
        self._tx("Old Cloud", "2025-01-01", 20)
        self._tx("Old Cloud", "2025-02-01", 20)
        self._tx("Old Cloud", "2025-03-01", 20)
        self._tx("Future Cloud", "2026-10-01", 20)
        self._tx("Future Cloud", "2026-11-01", 20)
        result = self.subscriptions.scan()
        self.assertEqual([s["merchant"] for s in result["items"]], [])
        self.assertEqual([s["merchant"] for s in result["candidates"]], ["Old Cloud"])

    def test_known_merchant_single_charge_is_candidate(self):
        self._tx("Netflix", "2026-09-01", 18)
        result = self.subscriptions.scan()
        self.assertEqual(len(result["candidates"]), 1)
        self.assertIn("posted charge", result["candidates"][0]["reason"])

    def test_scan_persists_calendar_anchor_and_manual_correction(self):
        self._tx("Anchor Cloud", "2026-01-31", 20)
        self._tx("Anchor Cloud", "2026-02-28", 20)
        self._tx("Anchor Cloud", "2026-03-31", 20)
        sub = self.subscriptions.scan()["candidates"][0]
        self.assertEqual(sub["billing_day"], 31)
        self.assertEqual(sub["next_due"], "2026-04-30")
        corrected = self.subscriptions.save({"id": sub["id"], "cadence": "quarterly", "next_due": "2027-01-31"})
        self.subscriptions.scan()
        reread = self.subscriptions.listing()["candidates"][0]
        self.assertEqual(reread["cadence"], "quarterly")
        self.assertEqual(reread["next_due"], "2027-01-31")
        self.assertEqual(corrected["next_due"], "2027-01-31")

    def test_custom_interval_update_is_merged_and_priced(self):
        sub = self.subscriptions.save({"merchant": "Custom Service", "scope": "personal", "account_id": "a", "amount": 10, "cadence": "custom", "custom_interval_days": 45, "next_due": "2026-09-10"})
        updated = self.subscriptions.save({"id": sub["id"], "amount": 12})
        self.assertEqual(updated["custom_interval_days"], 45)
        self.assertEqual(updated["monthly_cost"], 8.12)

    def test_plan_matches_exact_merchant_once_across_subscriptions(self):
        self._tx("Cloud Plus", "2026-09-01", 20)
        self.subscriptions.save({"merchant": "Cloud", "scope": "personal", "account_id": "a", "amount": 20, "cadence": "monthly", "next_due": "2026-09-01", "status": "active"})
        self.subscriptions.save({"merchant": "Cloud Plus", "scope": "personal", "account_id": "a", "amount": 20, "cadence": "monthly", "next_due": "2026-09-01", "status": "active"})
        plan = self.subscriptions.monthly_plan("personal", "2026-09")
        self.assertEqual(len(plan["paid_items"]), 1)
        self.assertEqual(len(plan["upcoming_items"]), 1)

    def test_save_validates_merged_scope_due_and_https(self):
        sub = self.subscriptions.save({"merchant": "Managed", "scope": "personal", "account_id": "a", "amount": 5, "cadence": "monthly", "next_due": "2026-09-10", "management_url": "https://example.test/manage"})
        with self.assertRaises(ValueError): self.subscriptions.save({"id": sub["id"], "scope": "business"})
        with self.assertRaises(ValueError): self.subscriptions.save({"id": sub["id"], "next_due": "09/10/2026"})
        with self.assertRaises(ValueError): self.subscriptions.save({"id": sub["id"], "management_url": "https://"})

    def test_projection_debt_is_independent_and_negative_return_stays_real(self):
        result = self.forecasts.project({"years": 1, "starting_cash": 100, "starting_investments": 100, "starting_debt": 100, "monthly_savings": 10, "monthly_investment": 5, "monthly_debt_payment": 20, "annual_return": -99, "debt_apr": 0})
        row = result["series"][0]
        self.assertEqual((row["cash"], row["investments"], row["debt"]), (220.0, 16.53, 0.0))
        self.assertTrue(all(isinstance(result["summary"][k], (int, float)) for k in ("conservative", "base", "optimistic")))

    def test_defaults_use_account_type_and_negative_balance_as_liability(self):
        self.db.ex("INSERT INTO accounts(id,name,type,subtype,scope,balance,created_at) VALUES(?,?,?,?,?,?,?)", ("credit-union", "First Credit Union checking", "depository", "checking", "personal", -50, "2026-01-01"))
        self.db.ex("INSERT INTO accounts(id,name,type,subtype,scope,balance,created_at) VALUES(?,?,?,?,?,?,?)", ("savings", "Credit Savings", "depository", "savings", "personal", 500, "2026-01-01"))
        d = self.forecasts.defaults("personal")
        self.assertEqual((d["starting_cash"], d["starting_debt"]), (500.0, 50.0))

    def test_scan_skips_unsupported_multi_year_custom_interval(self):
        self._tx("Rare Vendor", "2020-01-01", 20)
        self._tx("Rare Vendor", "2025-01-01", 20)
        result = self.subscriptions.scan()
        self.assertEqual(result["candidates"], [])
        self.assertEqual(self.db.q("SELECT * FROM subscriptions"), [])

    def test_next_due_edit_resets_anchor_unless_explicit(self):
        sub = self.subscriptions.save({"merchant": "Anchor", "scope": "personal", "account_id": "a", "amount": 5, "cadence": "monthly", "next_due": "2026-01-31"})
        updated = self.subscriptions.save({"id": sub["id"], "next_due": "2026-02-15"})
        self.assertEqual(updated["billing_day"], 15)

    def test_plan_excludes_future_posted_transactions_and_sorts_due(self):
        self._tx("Later", "2026-09-20", 10)
        self._tx("Soon", "2026-09-01", 10)
        self.subscriptions.save({"merchant": "Later", "scope": "personal", "account_id": "a", "amount": 10, "cadence": "monthly", "next_due": "2026-09-20", "status": "active"})
        self.subscriptions.save({"merchant": "Soon", "scope": "personal", "account_id": "a", "amount": 10, "cadence": "monthly", "next_due": "2026-09-10", "status": "active"})
        plan = self.subscriptions.monthly_plan("personal", "2026-09")
        self.assertEqual(plan["spent"], 10)
        self.assertEqual([x["due"] for x in plan["upcoming_items"]], ["2026-09-10", "2026-09-20"])

    def test_manual_no_account_subscription_is_reused_by_account_scan(self):
        self.subscriptions.save({"merchant": "Shared SaaS", "scope": "personal", "amount": 20, "cadence": "monthly", "next_due": "2026-09-05", "status": "active"})
        self._tx("Shared SaaS", "2026-08-05", 20)
        self._tx("Shared SaaS", "2026-09-05", 20)
        result = self.subscriptions.scan()
        self.assertEqual(len(self.db.q("SELECT * FROM subscriptions")), 1)
        self.assertEqual(result["items"][0]["account_id"], None)

    def test_ambiguous_manual_scope_wide_identity_is_not_duplicated(self):
        self.subscriptions.save({"merchant": "Ambiguous SaaS", "scope": "personal", "amount": 20, "cadence": "monthly", "next_due": "2026-09-05", "status": "active"})
        self.subscriptions.save({"merchant": "Ambiguous SaaS", "scope": "personal", "amount": 25, "cadence": "monthly", "next_due": "2026-09-05", "status": "active"})
        self._tx("Ambiguous SaaS", "2026-08-05", 20)
        self._tx("Ambiguous SaaS", "2026-09-05", 20)
        self.subscriptions.scan()
        self.assertEqual(len(self.db.q("SELECT * FROM subscriptions")), 2)

    def test_autoactivation_requires_regular_low_variation_supported_charges(self):
        for d in ("2026-07-01", "2026-08-01", "2026-09-01"):
            self._tx("Acme SaaS", d, 20)
        self._tx("Kroger", "2026-07-03", 83)
        self._tx("Kroger", "2026-08-04", 91)
        self._tx("Kroger", "2026-09-02", 77)
        self._tx("Variable Bill", "2026-07-10", 10)
        self._tx("Variable Bill", "2026-08-10", 25)
        self._tx("Variable Bill", "2026-09-10", 10)
        result = self.subscriptions.scan()
        self.assertEqual([s["merchant"] for s in result["items"]], ["Acme SaaS"])
        self.assertEqual({s["merchant"] for s in result["candidates"]}, {"Kroger", "Variable Bill"})

    def test_manual_price_change_surfaces_review_without_overwriting_amount(self):
        sub = self.subscriptions.save({"merchant": "Pricey SaaS", "scope": "personal", "account_id": "a", "amount": 20, "cadence": "monthly", "next_due": "2026-09-01", "status": "active"})
        self._tx("Pricey SaaS", "2026-08-01", 30)
        self._tx("Pricey SaaS", "2026-09-01", 30)
        result = self.subscriptions.scan()
        self.assertEqual(result["items"][0]["id"], sub["id"])
        self.assertEqual(result["items"][0]["amount"], 20)
        self.assertEqual(result["items"][0]["observed_amount"], 30)
        self.assertTrue(result["items"][0]["price_review"])
        self.assertEqual(self.subscriptions.listing()["price_reviews"][0]["id"], sub["id"])
        accepted = self.subscriptions.review(sub["id"], "accept_price")
        self.assertEqual((accepted["amount"], accepted["price_review"]), (30, False))

    def test_keep_price_suppresses_repeat_prompt_for_same_observation(self):
        sub = self.subscriptions.save({"merchant": "Stable SaaS", "scope": "personal", "account_id": "a", "amount": 20, "cadence": "monthly", "next_due": "2026-09-01", "status": "active"})
        self._tx("Stable SaaS", "2026-08-01", 30)
        self.subscriptions.scan()
        kept = self.subscriptions.review(sub["id"], "keep_price")
        self.assertEqual((kept["amount"], kept["ignored_price"], kept["price_review"]), (20, 30, False))
        result = self.subscriptions.scan()
        self.assertEqual(result["items"][0]["id"], sub["id"])
        self.assertEqual(result["items"][0]["price_review"], False)

    def test_debt_apr_is_nominal_apr_divided_by_twelve(self):
        row = self.forecasts.project({"years": 1, "starting_debt": 100, "debt_apr": 12})["series"][0]
        self.assertEqual(row["debt"], 112.68)

    def test_defaults_positive_credit_balance_is_an_asset_and_db_errors_raise(self):
        self.db.ex("INSERT INTO accounts(id,name,type,subtype,scope,balance,created_at) VALUES(?,?,?,?,?,?,?)", ("credit-refund", "Refund Credit", "credit", "credit card", "personal", 25, "2026-01-01"))
        d = self.forecasts.defaults("personal")
        self.assertEqual((d["starting_cash"], d["starting_investments"], d["starting_debt"]), (25.0, 0.0, 0.0))
        original_q = self.forecasts.db.q
        try:
            self.forecasts.db.q = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("database unavailable"))
            with self.assertRaises(RuntimeError): self.forecasts.defaults("personal")
        finally:
            self.forecasts.db.q = original_q

    def test_existing_unconfirmed_autoactive_detection_is_downgraded(self):
        sub = self.subscriptions.save({"merchant": "Noisy Grocery", "scope": "personal", "account_id": "a", "amount": 20, "cadence": "monthly", "next_due": "2026-09-01", "status": "active", "source": "detected"})
        for d, amount in (("2026-07-01", 20), ("2026-08-04", 27), ("2026-09-02", 15)):
            self._tx("Noisy Grocery", d, amount)
        result = self.subscriptions.scan()
        self.assertEqual(result["candidates"][0]["id"], sub["id"])

    def test_detected_active_price_change_stays_committed_and_surfaces_review(self):
        for d, amount in (("2026-07-04", 20), ("2026-08-04", 20), ("2026-09-04", 20)):
            self._tx("Detected SaaS", d, amount)
        sub = self.subscriptions.scan()["items"][0]
        self.db.ex("UPDATE transactions SET amount=-40 WHERE id=?", ("t20260904",))

        result = self.subscriptions.scan()
        self.assertEqual(result["items"][0]["id"], sub["id"])
        self.assertEqual(result["items"][0]["status"], "active")
        self.assertEqual(result["items"][0]["amount"], 20)
        self.assertEqual(result["items"][0]["observed_amount"], 40)
        self.assertTrue(result["items"][0]["price_review"])
        self.assertEqual(self.subscriptions.listing()["monthly_total"], 20)
        self.subscriptions.review(sub["id"], "accept_price")
        rescanned = self.subscriptions.scan()
        self.assertEqual((rescanned["items"][0]["amount"], rescanned["items"][0]["price_review"]), (40, False))
        self.assertEqual(self.subscriptions.listing()["monthly_total"], 40)

    def test_historical_networth_excludes_future_posted_transactions(self):
        self.db.ex("UPDATE accounts SET balance=100 WHERE id='a'")
        self.db.ex("INSERT INTO transactions(id,account_id,scope,amount,posted,name,pending,is_transfer,created_at) VALUES(?,?,?,?,?,?,?,?,?)", ("future", "a", "personal", 50, "2026-09-20", "Future income", 0, 0, "2026-09-04"))
        from unittest.mock import patch
        with patch.object(self.analytics, "month_list", return_value=[(2026, 8), (2026, 9)]):
            series = self.analytics.net_worth_series()
        self.assertEqual(series[0]["balance"], 100)
        self.assertEqual(series[1]["balance"], 100)


if __name__ == "__main__": unittest.main()
