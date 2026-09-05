import os
import tempfile
import unittest
from unittest.mock import patch

from backend import auth, db, scheduler


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.DATA_DIR = self.tmp.name
        db.DB_PATH = os.path.join(self.tmp.name, "ledger.db")
        db.CONFIG_PATH = os.path.join(self.tmp.name, "config.json")
        auth.init_schema()

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_setup_returns_a_session_and_persists_only_verifiers(self):
        token = auth.setup("correct horse battery staple")

        self.assertTrue(auth.configured())
        self.assertTrue(auth.validate(token))
        row = db.q1("SELECT * FROM auth_owner WHERE id=1")
        self.assertNotIn("correct horse battery staple", str(row))
        self.assertNotEqual(row["password_hash"], row["password_salt"])
        session = db.q1("SELECT token_hash,expires_at FROM auth_sessions")
        self.assertNotEqual(session["token_hash"], token)
        self.assertEqual(len(session["token_hash"]), 64)
        with self.assertRaises(ValueError):
            auth.setup("another password that is long enough")

    def test_setup_rejects_short_passwords_and_cookie_helpers_are_restrictive(self):
        with self.assertRaises(ValueError):
            auth.setup("too short")

        with self.assertRaises(ValueError):
            auth.setup("correct horse battery staple", session_ttl=0)
        self.assertFalse(auth.configured())

        token = auth.setup("correct horse battery staple")
        cookie = auth.make_session_cookie(token, secure=True)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        self.assertIn("Secure", cookie)
        self.assertEqual(auth.token_from_cookie("other=x; ledger_session=" + token + "; theme=dark"), token)
        self.assertIsNone(auth.token_from_cookie("ledger_session="))

    def test_login_uses_constant_time_verification_and_logout_revokes_token(self):
        auth.setup("correct horse battery staple")

        with self.assertRaises(ValueError):
            auth.login("wrong password", remote="127.0.0.1")
        token = auth.login("correct horse battery staple", remote="127.0.0.1")
        self.assertIsInstance(token, str)
        self.assertTrue(auth.validate(token))
        auth.logout(token)
        self.assertFalse(auth.validate(token))

    def test_login_rate_limit_blocks_password_guessing(self):
        auth.setup("correct horse battery staple")

        for _ in range(auth.MAX_FAILURES):
            with self.assertRaises(ValueError):
                auth.login("wrong password", remote="198.51.100.10")
        with self.assertRaises(ValueError):
            auth.login("correct horse battery staple", remote="198.51.100.10")

    def test_sessions_expire(self):
        with patch.object(auth.time, "time", side_effect=[1000.0, 1000.0, 1000.0, 1000.0, 1000.0, 1000.0, 1000.0, 1000.0]):
            token = auth.setup("correct horse battery staple", session_ttl=10)
            self.assertTrue(auth.validate(token))
        with patch.object(auth.time, "time", return_value=1011.0):
            self.assertFalse(auth.validate(token))

    def test_scheduler_status_is_safe_and_sync_is_disabled_in_tests(self):
        with patch.object(scheduler, "_test_mode", return_value=True):
            result = scheduler.sync_all()
            status = scheduler.status()

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["items"], [])
        self.assertIn("disabled", result["message"])
        self.assertIsInstance(status["items"], list)
        self.assertIn("message", status)

    def test_scheduler_worker_runs_again_after_a_run_level_error(self):
        class StopAfterTwoWaits:
            def __init__(self):
                self.waits = 0

            def is_set(self):
                return False

            def wait(self, _seconds):
                self.waits += 1
                return self.waits >= 2

        stop = StopAfterTwoWaits()
        with patch.object(scheduler, "_test_mode", return_value=False), \
                patch.object(scheduler, "_interval_minutes", return_value=1), \
                patch.object(scheduler, "sync_all", side_effect=[RuntimeError("provider token"), {"status": "ok"}]) as sync:
            scheduler._worker(stop)

        self.assertEqual(sync.call_count, 2)
        self.assertEqual(stop.waits, 2)


if __name__ == "__main__":
    unittest.main()
