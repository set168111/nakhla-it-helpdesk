"""OFFLINE unit tests for app/auth.py (local demo login). Temporary databases, a fake clock, no network.

Run: python -B -m unittest tests.test_auth_service -v
"""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from app.auth import (AuthService, LoginThrottled, Principal, hash_password, legacy_action_report,
                      legacy_session_ids, verify_password)
from app.storage import Store

PASSWORD = "correct-horse-battery"


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


def service(tmp: Path, clock: Clock | None = None, **options) -> AuthService:
    auth = AuthService(tmp / "auth.sqlite3", clock=clock or Clock(), **options)
    auth.provision_employee("E-1", "Sara.Mikhail@nakhla.example", "Sara Mikhail", "Support")
    auth.set_password("E-1", "demo", PASSWORD)
    auth.provision_employee("E-2", "omar.farah@nakhla.example", "Omar Farah", "Sales")
    auth.set_password("E-2", "demo", "another-long-password")
    auth.set_admin_password("admin-only-password")
    return auth


class PasswordHashTests(unittest.TestCase):
    def test_salted_scrypt_hashes_verify_and_differ_per_call(self):
        first, second = hash_password(PASSWORD), hash_password(PASSWORD)
        self.assertNotEqual(first, second)                              # random salt
        self.assertTrue(first.startswith("scrypt$"))
        self.assertNotIn(PASSWORD, first)
        self.assertTrue(verify_password(PASSWORD, first))
        self.assertFalse(verify_password(PASSWORD + "x", first))
        self.assertFalse(verify_password("", first))

    def test_malformed_or_foreign_hashes_never_verify(self):
        for stored in ("", "plain", "md5$1$2$3$4$5", "scrypt$x$8$1$AAAA$AAAA", "scrypt$16384$8$1$!!$!!"):
            self.assertFalse(verify_password(PASSWORD, stored), stored)


class LoginTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock = Clock()
        self.auth = service(Path(self.tmp.name), self.clock)

    def test_login_returns_stable_internal_identity_and_is_case_insensitive_on_email(self):
        token, expires, principal = self.auth.login("  SARA.mikhail@nakhla.example ", PASSWORD)
        self.assertEqual(principal, Principal("E-1", "sara.mikhail@nakhla.example", "Sara Mikhail", "Support"))
        self.assertGreater(expires, self.clock.now)
        self.assertEqual(self.auth.authenticate(token), principal)

    def test_every_failure_is_the_same_generic_none(self):
        self.auth.provision_employee("E-3", "nopassword@nakhla.example", "No Password", "Sales")
        with closing(sqlite3.connect(self.auth.path)) as db:
            db.execute("UPDATE employees SET active=0 WHERE employee_id=?", ("E-2",))
            db.commit()
        for email, password in (("sara.mikhail@nakhla.example", "wrong"), ("nobody@nakhla.example", PASSWORD),
                                ("nopassword@nakhla.example", PASSWORD), ("omar.farah@nakhla.example", "another-long-password"),
                                ("", ""), ("sara.mikhail@nakhla.example", "")):
            self.assertIsNone(self.auth.login(email, password), (email, password))

    def test_token_is_opaque_random_and_only_its_hash_is_stored(self):
        token = self.auth.login("sara.mikhail@nakhla.example", PASSWORD)[0]
        other = self.auth.login("sara.mikhail@nakhla.example", PASSWORD)[0]
        self.assertNotEqual(token, other)
        self.assertGreaterEqual(len(token), 40)
        with closing(sqlite3.connect(self.auth.path)) as db:
            dump = "\n".join(str(row) for table in ("login_sessions", "credentials", "employees", "admin_credential")
                             for row in db.execute(f"SELECT * FROM {table}"))
        self.assertNotIn(token, dump)
        self.assertNotIn(PASSWORD, dump)

    def test_unknown_token_none_and_empty(self):
        for token in (None, "", "garbage", "x" * 60):
            self.assertIsNone(self.auth.authenticate(token))


class ExpiryAndLogoutTests(LoginTests):
    def test_absolute_expiry_ends_the_login(self):
        auth = service(Path(self.tmp.name) / "abs", self.clock, absolute_ttl=600, idle_ttl=10_000)
        token = auth.login("sara.mikhail@nakhla.example", PASSWORD)[0]
        self.clock.now += 599
        self.assertIsNotNone(auth.authenticate(token))
        self.clock.now += 2
        self.assertIsNone(auth.authenticate(token))

    def test_idle_expiry_slides_with_activity_but_never_past_the_absolute_limit(self):
        auth = service(Path(self.tmp.name) / "idle", self.clock, absolute_ttl=3000, idle_ttl=100)
        token = auth.login("sara.mikhail@nakhla.example", PASSWORD)[0]
        for _ in range(5):
            self.clock.now += 90
            self.assertIsNotNone(auth.authenticate(token))         # activity keeps it alive
        self.clock.now += 101
        self.assertIsNone(auth.authenticate(token))                # idle too long
        token = auth.login("sara.mikhail@nakhla.example", PASSWORD)[0]
        for _ in range(40):
            self.clock.now += 90
            if auth.authenticate(token) is None:
                break
        self.assertIsNone(auth.authenticate(token))                # absolute limit wins

    def test_logout_invalidates_only_that_login_session(self):
        first = self.auth.login("sara.mikhail@nakhla.example", PASSWORD)[0]
        second = self.auth.login("sara.mikhail@nakhla.example", PASSWORD)[0]
        self.assertTrue(self.auth.logout(first))
        self.assertIsNone(self.auth.authenticate(first))
        self.assertIsNotNone(self.auth.authenticate(second))
        self.assertFalse(self.auth.logout(first))                   # idempotent: nothing left to revoke
        self.assertFalse(self.auth.logout(None))

    def test_deactivated_employee_loses_existing_sessions(self):
        token = self.auth.login("omar.farah@nakhla.example", "another-long-password")[0]
        with closing(sqlite3.connect(self.auth.path)) as db:
            db.execute("UPDATE employees SET active=0 WHERE employee_id=?", ("E-2",))
            db.commit()
        self.assertIsNone(self.auth.authenticate(token))


class ThrottleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock = Clock()
        self.auth = service(Path(self.tmp.name), self.clock, max_failures=3, failure_window=600, lock_seconds=300)

    def fail(self, email="sara.mikhail@nakhla.example", times=3):
        for _ in range(times):
            self.assertIsNone(self.auth.login(email, "wrong"))

    def test_repeated_failures_lock_the_account_even_for_the_right_password(self):
        self.fail()
        with self.assertRaises(LoginThrottled) as locked:
            self.auth.login("sara.mikhail@nakhla.example", PASSWORD)
        self.assertGreater(locked.exception.retry_after, 0)
        self.assertLessEqual(locked.exception.retry_after, 301)
        self.assertIsNotNone(self.auth.login("omar.farah@nakhla.example", "another-long-password"))   # others unaffected

    def test_lock_expires_and_success_resets_the_counter(self):
        self.fail()
        self.clock.now += 301
        self.assertIsNotNone(self.auth.login("sara.mikhail@nakhla.example", PASSWORD))
        self.fail(times=2)                                             # counter restarted: two failures do not lock
        self.assertIsNotNone(self.auth.login("sara.mikhail@nakhla.example", PASSWORD))

    def test_failures_outside_the_window_do_not_accumulate(self):
        self.fail(times=2)
        self.clock.now += 601
        self.fail(times=2)
        self.assertIsNotNone(self.auth.login("sara.mikhail@nakhla.example", PASSWORD))

    def test_unknown_accounts_are_throttled_exactly_like_known_ones(self):
        self.fail(email="ghost@nakhla.example")
        with self.assertRaises(LoginThrottled):
            self.auth.login("ghost@nakhla.example", "anything")

    def test_global_ceiling_pauses_distributed_guessing(self):
        auth = service(Path(self.tmp.name) / "g", self.clock, max_failures=50, global_max_failures=4, global_lock_seconds=30)
        for index in range(4):
            self.assertIsNone(auth.login(f"user{index}@nakhla.example", "wrong"))
        with self.assertRaises(LoginThrottled):
            auth.login("sara.mikhail@nakhla.example", PASSWORD)
        self.clock.now += 31
        self.assertIsNotNone(auth.login("sara.mikhail@nakhla.example", PASSWORD))

    def test_admin_login_is_throttled_separately(self):
        for _ in range(3):
            self.assertIsNone(self.auth.admin_login("wrong"))
        with self.assertRaises(LoginThrottled):
            self.auth.admin_login("admin-only-password")
        self.assertIsNotNone(self.auth.login("sara.mikhail@nakhla.example", PASSWORD))   # employees unaffected


class AdminSeparationTests(LoginTests):
    def test_admin_and_employee_sessions_are_not_interchangeable(self):
        admin_token, _ = self.auth.admin_login("admin-only-password")
        employee_token = self.auth.login("sara.mikhail@nakhla.example", PASSWORD)[0]
        self.assertTrue(self.auth.authenticate_admin(admin_token))
        self.assertIsNone(self.auth.authenticate(admin_token))          # admin never becomes an employee
        self.assertFalse(self.auth.authenticate_admin(employee_token))  # employee never becomes admin
        self.assertIsNone(self.auth.admin_login(PASSWORD))
        self.assertIsNone(self.auth.login("demo-admin", "admin-only-password"))

    def test_admin_session_expires_and_logs_out(self):
        token, _ = self.auth.admin_login("admin-only-password")
        self.assertTrue(self.auth.logout(token))
        self.assertFalse(self.auth.authenticate_admin(token))
        token, _ = self.auth.admin_login("admin-only-password")
        self.clock.now += 3601
        self.assertFalse(self.auth.authenticate_admin(token))


class OwnershipTests(LoginTests):
    def test_claim_confirm_refuse_and_never_by_conversation_id_alone(self):
        self.assertTrue(self.auth.claim_session("conv-1", "E-1"))
        self.assertTrue(self.auth.claim_session("conv-1", "E-1"))       # the owner again
        self.assertFalse(self.auth.claim_session("conv-1", "E-2"))      # knowing the id is not enough
        self.assertTrue(self.auth.owns_session("conv-1", "E-1"))
        self.assertFalse(self.auth.owns_session("conv-1", "E-2"))
        self.assertFalse(self.auth.owns_session("never-seen", "E-1"))   # an unclaimed id owns nothing

    def test_legacy_sessions_are_retired_not_adopted_and_claims_are_untouched(self):
        self.auth.claim_session("fresh", "E-1")
        self.assertEqual(self.auth.retire_legacy_sessions(["old-1", "old-2", "fresh"]), 2)   # "fresh" already owned
        self.assertEqual(self.auth.retire_legacy_sessions(["old-1", "old-2"]), 0)            # idempotent
        for employee in ("E-1", "E-2"):
            self.assertFalse(self.auth.claim_session("old-1", employee))     # nobody can adopt it
            self.assertFalse(self.auth.owns_session("old-2", employee))
        self.assertTrue(self.auth.owns_session("fresh", "E-1"))


class LegacyInspectionTests(unittest.TestCase):
    def test_read_only_listing_and_action_report_do_not_modify_the_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "helpdesk.sqlite3"
            store = Store(db_path)
            store.save_session("legacy-a", {"email": "sara.mikhail@nakhla.example"})
            store.save_session("legacy-b", {"email": "omar.farah@nakhla.example"})
            with closing(sqlite3.connect(db_path)) as db:
                for index, status in enumerate(("failed", "committing", "unknown", "pending_recovery", "succeeded")):
                    db.execute("INSERT INTO actions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                               (f"act-x{index}", "legacy-a", "{}", "h", "s", "f", status, 1.0, 9e12, None, None))
                db.commit()
                db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            before = db_path.read_bytes()
            self.assertEqual(sorted(legacy_session_ids(db_path)), ["legacy-a", "legacy-b"])
            report = legacy_action_report(db_path, now=2.0)
            self.assertEqual(sorted(report["needs_reconciliation"]), ["act-x1", "act-x2", "act-x3"])
            self.assertEqual(report["by_status"]["failed"], 1)
            self.assertEqual(report["sessions"], 2)
            self.assertEqual(db_path.read_bytes(), before)                # byte-identical: nothing written
        self.assertEqual(legacy_session_ids(Path("does-not-exist.sqlite3")), [])


if __name__ == "__main__":
    unittest.main()
