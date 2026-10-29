"""Durable, transactional session and immutable approval records."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


def canonical(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class Store:
    def __init__(self, path: str | Path = "data/helpdesk.sqlite3"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, state TEXT NOT NULL, updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS actions(
              id TEXT PRIMARY KEY, session_id TEXT NOT NULL, payload TEXT NOT NULL,
              payload_hash TEXT NOT NULL, summary TEXT NOT NULL, fingerprint TEXT NOT NULL,
              status TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL,
              result TEXT, error TEXT);
            CREATE INDEX IF NOT EXISTS actions_session ON actions(session_id,created);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def get_session(self, session_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT state FROM sessions WHERE id=?", (session_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def save_session(self, session_id: str, state: dict):
        with self.connect() as db:
            db.execute("INSERT INTO sessions VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state,updated=excluded.updated",
                       (session_id, canonical(state), time.time()))

    @staticmethod
    def _action(row) -> dict | None:
        if not row:
            return None
        value = dict(row)
        value["action_id"] = value.pop("id")
        for key in ("payload", "result", "error"):
            value[key] = json.loads(value[key]) if value[key] else None
        value["type"] = "create_ticket"
        return value

    def get_action(self, action_id: str) -> dict | None:
        with self.connect() as db:
            return self._action(db.execute("SELECT * FROM actions WHERE id=?", (action_id,)).fetchone())

    def latest_action(self, session_id: str) -> dict | None:
        with self.connect() as db:
            return self._action(db.execute("SELECT * FROM actions WHERE session_id=? ORDER BY created DESC LIMIT 1", (session_id,)).fetchone())

    def supersede(self, session_id: str):
        with self.connect() as db:
            db.execute("UPDATE actions SET status='superseded' WHERE session_id=? AND status IN ('pending','failed')", (session_id,))

    def propose(self, session_id: str, payload: dict, summary: str | None = None,
                fingerprint: str = "", ttl: float = 1800) -> dict:
        encoded = canonical(payload)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        action_id = "act-" + uuid.uuid4().hex
        now = time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            unresolved = db.execute("SELECT id FROM actions WHERE session_id=? AND status IN ('committing','unknown','pending_recovery')", (session_id,)).fetchone()
            if unresolved:
                raise ValueError("An earlier write has an unknown outcome; reconcile it before making another draft.")
            db.execute("UPDATE actions SET status='superseded' WHERE session_id=? AND status IN ('pending','failed')", (session_id,))
            db.execute("INSERT INTO actions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                       (action_id, session_id, encoded, digest, summary or encoded, fingerprint,
                        "pending", now, now + ttl, None, None))
        return self.get_action(action_id)

    def claim(self, session_id: str, action_id: str) -> tuple[str, dict | None]:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            action = self._action(db.execute("SELECT * FROM actions WHERE id=? AND session_id=?", (action_id, session_id)).fetchone())
            if not action:
                return "unknown_action", None
            if action["status"] not in {"pending", "pending_recovery"}:
                return action["status"], action
            if action["expires"] <= time.time():
                outcome = "unknown" if action["status"] == "pending_recovery" else "expired"
                db.execute("UPDATE actions SET status=? WHERE id=?", (outcome, action_id))
                return outcome, action
            if hashlib.sha256(canonical(action["payload"]).encode()).hexdigest() != action["payload_hash"]:
                db.execute("UPDATE actions SET status='invalid' WHERE id=?", (action_id,))
                return "invalid", action
            db.execute("UPDATE actions SET status='committing' WHERE id=?", (action_id,))
            return "claimed", action

    def finish(self, action_id: str, status: str, result: dict | None = None, error: dict | None = None):
        if status not in {"succeeded", "failed", "unknown", "rejected", "superseded", "invalid", "expired"}:
            raise ValueError("Invalid action terminal status")
        with self.connect() as db:
            db.execute("UPDATE actions SET status=?,result=?,error=? WHERE id=? AND status IN ('committing','pending','pending_recovery','failed','unknown')",
                       (status, canonical(result) if result else None, canonical(error) if error else None, action_id))

    def reject(self, session_id: str, action_id: str) -> bool:
        with self.connect() as db:
            changed = db.execute("UPDATE actions SET status='rejected' WHERE id=? AND session_id=? AND status='pending'",
                                 (action_id, session_id)).rowcount
        return bool(changed)

    def reopen(self, session_id: str, action_id: str) -> dict | None:
        """Explicit user retry only; preserve canonical bytes and idempotency identity."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            action = self._action(db.execute("SELECT * FROM actions WHERE id=? AND session_id=?", (action_id, session_id)).fetchone())
            if not action or action["status"] not in {"failed", "unknown", "committing"}:
                return None
            # A committing action may belong to another active request. It must not be reclaimed.
            if action["status"] == "committing":
                return None
            reopened_status = "pending_recovery" if action["status"] == "unknown" else "pending"
            db.execute("UPDATE actions SET status=?,expires=? WHERE id=?", (reopened_status, time.time() + 1800, action_id))
        return self.get_action(action_id)

    def recover_interrupted(self):
        """Call once at application startup, before serving requests."""
        with self.connect() as db:
            db.execute("UPDATE actions SET status='unknown' WHERE status='committing'")

    def purge_history(self, days: float = 7) -> dict:
        """Explicit startup retention. Never remove unresolved approvals/recovery state."""
        if days <= 0:
            raise ValueError("Retention must be positive")
        resolved = ("succeeded", "rejected", "superseded", "invalid", "expired")
        placeholders = ",".join("?" for _ in resolved)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            cutoff = time.time() - days * 86400
            actions = db.execute(f"DELETE FROM actions WHERE created<? AND status IN ({placeholders})", (cutoff, *resolved)).rowcount
            sessions = db.execute("DELETE FROM sessions WHERE updated<? AND id NOT IN (SELECT session_id FROM actions)", (cutoff,)).rowcount
        return {"sessions_deleted": sessions, "actions_deleted": actions}

    def purge(self, age_seconds: float = 7 * 86400):
        return self.purge_history(age_seconds / 86400)
