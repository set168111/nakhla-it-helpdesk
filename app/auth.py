"""Local demo authentication: individual employees, hashed passwords, revocable sessions.

Standard library only (hashlib.scrypt, hmac, secrets, sqlite3): no installed maintained
auth package offers server-side revocable sessions, so the small primitives are used
directly. Passwords are stored only as salted scrypt hashes; login sessions are opaque
random tokens stored only as SHA-256 hashes, with absolute and idle expiry and logout
revocation. Ownership of conversations is bound to the stable internal employee_id,
never to an email string or to a conversation id.

LOCAL DEMO ONLY: this is not a production identity provider. The production path is
company OIDC (the same Principal interface, a different verifier).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1
GENERIC_FAILURE = "Invalid email or password."


@dataclass(frozen=True)
class Principal:
    """A verified employee. employee_id is the stable internal identity."""
    employee_id: str
    email: str
    name: str
    department: str


class LoginThrottled(Exception):
    def __init__(self, retry_after: int):
        super().__init__("too many attempts")
        self.retry_after = retry_after


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    b64 = lambda raw: base64.b64encode(raw).decode("ascii")
    return "$".join(["scrypt", str(SCRYPT_N), str(SCRYPT_R), str(SCRYPT_P), b64(salt), b64(digest)])


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode("utf-8"), salt=base64.b64decode(salt),
                                n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


_DUMMY_HASH = hash_password("not-a-real-password")   # equalises work for unknown accounts


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


SCHEMA = """
CREATE TABLE IF NOT EXISTS employees(
  employee_id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
  department TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS credentials(
  employee_id TEXT NOT NULL, kind TEXT NOT NULL, hash TEXT NOT NULL, created REAL NOT NULL,
  PRIMARY KEY(employee_id, kind));
CREATE TABLE IF NOT EXISTS admin_credential(id INTEGER PRIMARY KEY CHECK(id=1), hash TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS login_sessions(
  token_hash TEXT PRIMARY KEY, subject_type TEXT NOT NULL, subject_id TEXT NOT NULL,
  created REAL NOT NULL, last_seen REAL NOT NULL, expires REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS login_attempts(
  key TEXT PRIMARY KEY, failures INTEGER NOT NULL, window_start REAL NOT NULL, locked_until REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS session_owners(
  session_id TEXT PRIMARY KEY, employee_id TEXT, retired INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL);
"""


class AuthService:
    def __init__(self, path: str | Path = "data/auth.sqlite3", *, clock: Callable[[], float] = time.time,
                 absolute_ttl: float = 8 * 3600, idle_ttl: float = 30 * 60,
                 admin_absolute_ttl: float = 3600, admin_idle_ttl: float = 20 * 60,
                 max_failures: int = 5, failure_window: float = 600, lock_seconds: float = 300,
                 global_max_failures: int = 60, global_window: float = 300, global_lock_seconds: float = 30):
        self.path = Path(path)
        self.clock = clock
        self.absolute_ttl, self.idle_ttl = absolute_ttl, idle_ttl
        self.admin_absolute_ttl, self.admin_idle_ttl = admin_absolute_ttl, admin_idle_ttl
        self.max_failures, self.failure_window, self.lock_seconds = max_failures, failure_window, lock_seconds
        self.global_max_failures, self.global_window, self.global_lock_seconds = global_max_failures, global_window, global_lock_seconds
        self._memory = None
        if str(path) == ":memory:":
            self._memory = sqlite3.connect(":memory:", check_same_thread=False)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def _db(self):
        if self._memory is not None:
            db, owned = self._memory, False
        else:
            db, owned = sqlite3.connect(self.path, timeout=10), True
            db.execute("PRAGMA journal_mode=WAL")
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            if owned:
                db.close()

    # ---- provisioning (setup script and tests; never reachable over HTTP) -----------------
    def provision_employee(self, employee_id: str, email: str, name: str, department: str) -> None:
        with self._db() as db:
            db.execute("INSERT INTO employees(employee_id,email,name,department) VALUES(?,?,?,?) "
                       "ON CONFLICT(employee_id) DO UPDATE SET email=excluded.email,name=excluded.name,department=excluded.department",
                       (employee_id, email.strip().lower(), name, department))

    def set_password(self, employee_id: str, kind: str, password: str) -> None:
        with self._db() as db:
            db.execute("INSERT INTO credentials(employee_id,kind,hash,created) VALUES(?,?,?,?) "
                       "ON CONFLICT(employee_id,kind) DO UPDATE SET hash=excluded.hash,created=excluded.created",
                       (employee_id, kind, hash_password(password), self.clock()))

    def set_admin_password(self, password: str) -> None:
        with self._db() as db:
            db.execute("INSERT INTO admin_credential(id,hash,created) VALUES(1,?,?) "
                       "ON CONFLICT(id) DO UPDATE SET hash=excluded.hash,created=excluded.created",
                       (hash_password(password), self.clock()))

    def employee_count(self) -> int:
        with self._db() as db:
            return db.execute("SELECT COUNT(*) FROM employees").fetchone()[0]

    # ---- bounded login attempts ----------------------------------------------------------
    @staticmethod
    def _check_throttle(db, key: str, now: float) -> None:
        row = db.execute("SELECT locked_until FROM login_attempts WHERE key=?", (key,)).fetchone()
        if row and row["locked_until"] > now:
            raise LoginThrottled(int(row["locked_until"] - now) + 1)

    @staticmethod
    def _record(db, key: str, now: float, *, window: float, limit: int, lock: float, success: bool) -> None:
        if success:
            db.execute("DELETE FROM login_attempts WHERE key=?", (key,))
            return
        row = db.execute("SELECT failures,window_start FROM login_attempts WHERE key=?", (key,)).fetchone()
        if not row or now - row["window_start"] > window:
            failures, start = 1, now
        else:
            failures, start = row["failures"] + 1, row["window_start"]
        locked = now + lock if failures >= limit else 0
        db.execute("INSERT INTO login_attempts(key,failures,window_start,locked_until) VALUES(?,?,?,?) "
                   "ON CONFLICT(key) DO UPDATE SET failures=excluded.failures,window_start=excluded.window_start,locked_until=excluded.locked_until",
                   (key, failures, start, locked))

    def _guarded(self, account_key: str, verify: Callable[[], bool]) -> bool:
        """Run one credential check under the per-account and the global attempt limits."""
        now = self.clock()
        with self._db() as db:
            self._check_throttle(db, account_key, now)
            self._check_throttle(db, "global", now)
        ok = verify()
        with self._db() as db:
            self._record(db, account_key, now, window=self.failure_window, limit=self.max_failures,
                         lock=self.lock_seconds, success=ok)
            if not ok:
                self._record(db, "global", now, window=self.global_window, limit=self.global_max_failures,
                             lock=self.global_lock_seconds, success=False)
        return ok

    # ---- employee login sessions ---------------------------------------------------------
    def _issue(self, subject_type: str, subject_id: str, ttl: float) -> tuple[str, float]:
        token, now = secrets.token_urlsafe(32), self.clock()
        with self._db() as db:
            db.execute("INSERT INTO login_sessions(token_hash,subject_type,subject_id,created,last_seen,expires,revoked) VALUES(?,?,?,?,?,?,0)",
                       (_token_hash(token), subject_type, subject_id, now, now, now + ttl))
        return token, now + ttl

    def login(self, email: str, password: str) -> tuple[str, float, Principal] | None:
        """Verified login. None for every failure (generic); LoginThrottled when locked out."""
        email = (email or "").strip().lower()[:120]
        with self._db() as db:
            row = db.execute("SELECT * FROM employees WHERE email=? AND active=1", (email,)).fetchone()
            hashes = ([r["hash"] for r in db.execute("SELECT hash FROM credentials WHERE employee_id=?", (row["employee_id"],))]
                      if row else [])

        def verify() -> bool:
            # Always two scrypt checks (demo + eval credential kinds), so a known and an unknown account cost the same.
            results = [verify_password(password or "", stored) for stored in (hashes + [_DUMMY_HASH, _DUMMY_HASH])[:2]]
            return bool(row) and any(results[:len(hashes)])

        if not self._guarded("emp:" + email, verify):
            return None
        token, expires = self._issue("employee", row["employee_id"], self.absolute_ttl)
        return token, expires, Principal(row["employee_id"], row["email"], row["name"], row["department"])

    def authenticate(self, token: str | None) -> Principal | None:
        if not token:
            return None
        now = self.clock()
        with self._db() as db:
            session = db.execute("SELECT * FROM login_sessions WHERE token_hash=? AND subject_type='employee' AND revoked=0",
                                 (_token_hash(token),)).fetchone()
            if not session or session["expires"] <= now or now - session["last_seen"] > self.idle_ttl:
                return None
            employee = db.execute("SELECT * FROM employees WHERE employee_id=? AND active=1", (session["subject_id"],)).fetchone()
            if not employee:
                return None
            db.execute("UPDATE login_sessions SET last_seen=? WHERE token_hash=?", (now, session["token_hash"]))
        return Principal(employee["employee_id"], employee["email"], employee["name"], employee["department"])

    def logout(self, token: str | None) -> bool:
        if not token:
            return False
        with self._db() as db:
            return bool(db.execute("UPDATE login_sessions SET revoked=1 WHERE token_hash=? AND revoked=0",
                                   (_token_hash(token),)).rowcount)

    # ---- separate demo-admin credential and sessions (never usable as an employee) --------
    def admin_login(self, password: str) -> tuple[str, float] | None:
        with self._db() as db:
            row = db.execute("SELECT hash FROM admin_credential WHERE id=1").fetchone()
        stored = row["hash"] if row else _DUMMY_HASH
        if not self._guarded("admin", lambda: bool(row) and verify_password(password or "", stored)):
            return None
        return self._issue("admin", "demo-admin", self.admin_absolute_ttl)

    def authenticate_admin(self, token: str | None) -> bool:
        if not token:
            return False
        now = self.clock()
        with self._db() as db:
            session = db.execute("SELECT * FROM login_sessions WHERE token_hash=? AND subject_type='admin' AND revoked=0",
                                 (_token_hash(token),)).fetchone()
            if not session or session["expires"] <= now or now - session["last_seen"] > self.admin_idle_ttl:
                return False
            db.execute("UPDATE login_sessions SET last_seen=? WHERE token_hash=?", (now, session["token_hash"]))
        return True

    # ---- conversation ownership ----------------------------------------------------------
    def claim_session(self, session_id: str, employee_id: str) -> bool:
        """Atomically claim a new conversation id, or confirm ownership of an existing one.
        A conversation id alone never grants access: foreign and retired ids are refused."""
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT employee_id,retired FROM session_owners WHERE session_id=?", (session_id,)).fetchone()
            if row is None:
                db.execute("INSERT INTO session_owners(session_id,employee_id,retired,created) VALUES(?,?,0,?)",
                           (session_id, employee_id, self.clock()))
                return True
            return row["employee_id"] == employee_id and not row["retired"]

    def owns_session(self, session_id: str, employee_id: str) -> bool:
        with self._db() as db:
            row = db.execute("SELECT employee_id,retired FROM session_owners WHERE session_id=?", (session_id,)).fetchone()
        return bool(row) and row["employee_id"] == employee_id and not row["retired"]

    def retire_legacy_sessions(self, session_ids: Iterable[str]) -> int:
        """Mark conversations that existed before authentication as retired. Their stored data is
        untouched and they are never adopted by an employee, whatever email they contain."""
        added = 0
        with self._db() as db:
            for session_id in session_ids:
                added += db.execute("INSERT OR IGNORE INTO session_owners(session_id,employee_id,retired,created) VALUES(?,NULL,1,?)",
                                    (session_id, self.clock())).rowcount
        return added

    def purge_expired(self) -> int:
        cutoff = self.clock() - 7 * 86400
        with self._db() as db:
            return db.execute("DELETE FROM login_sessions WHERE expires<? OR (revoked=1 AND last_seen<?)", (cutoff, cutoff)).rowcount


def legacy_session_ids(helpdesk_db: str | Path) -> list[str]:
    """Conversation ids already stored by the application, read-only."""
    path = Path(helpdesk_db)
    if not path.exists():
        return []
    db = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        return [row[0] for row in db.execute("SELECT id FROM sessions")]
    except sqlite3.DatabaseError:
        return []
    finally:
        db.close()


def legacy_action_report(helpdesk_db: str | Path, *, now: float | None = None) -> dict:
    """Read-only inspection of the stored actions that belong to retired legacy conversations."""
    now = time.time() if now is None else now
    db = sqlite3.connect(f"file:{Path(helpdesk_db).as_posix()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        by_status = {r["status"]: r["n"] for r in db.execute("SELECT status,COUNT(*) AS n FROM actions GROUP BY status")}
        needs = [r["id"] for r in db.execute("SELECT id FROM actions WHERE status IN ('committing','unknown','pending_recovery')")]
        live_pending = [r["id"] for r in db.execute("SELECT id FROM actions WHERE status='pending' AND expires>?", (now,))]
        return {"by_status": by_status, "needs_reconciliation": needs, "unexpired_pending": live_pending,
                "sessions": db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]}
    finally:
        db.close()
