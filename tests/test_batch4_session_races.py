"""OFFLINE shared-session and approval-race tests (batch 4: SES-T2, APP-T3).

Deterministic only: scripted model, fake MCP directory, temporary stores,
production create_app wiring. No services, no provider calls.

Valid outcomes are derived from the code, not assumed:
- A recall question supersedes pending actions and answers from stored session
  statements (app/agent.py conversation-recall branch).
- A same-session message on a NEW topic resets the in-progress issue context
  (new-issue heuristic); a same-topic message BLENDS into one context.
- storage.reject only transitions 'pending' rows; claim() transitions
  pending->committing and marks time-expired rows 'expired'; reopen() never
  resurrects rejected/expired/succeeded actions.

Honest framing: session_id is the ONLY boundary between clients; it is
client-chosen and unauthenticated. Everything demonstrated here about a
"second client" is available to anyone who knows or guesses a session id.
That is the documented asserted-identity limitation, not a new defect.

Run: python -m unittest tests.test_batch4_session_races -v
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from app.approvals import Approvals
from tests.auth_helpers import AuthedAsyncClient, AuthedTestClient, create_test_app
from app.storage import Store
from tests.test_agent_workflow import ANSWER, FakeRetrieval, ScriptedWorkflow
from tests.test_identity_session_security import DRAFT, DirectoryMCP, LOCKOUT_MSG, REVIEW_OK, SARA

ALREADY_USED = "No new write was sent"
DRAFT_SCRIPT = ({"action": "retrieve", "query": "lockout"}, DRAFT, REVIEW_OK)


class Batch4Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.store = Store(self.data / "state.sqlite3")
        self.mcp = DirectoryMCP()
        self.approvals = Approvals(self.store, self.mcp)

    def make_app(self, *script):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}):
            self.runtime = ScriptedWorkflow(self.store, self.mcp, FakeRetrieval(), self.approvals,
                                            data_dir=self.data, script=script)
        return create_test_app(self.runtime)

    def chat(self, client, session_id, message):
        response = client.post("/api/chat", json={
            "session_id": session_id, "message": message, "user": {"email": SARA["email"]}})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def pending_draft(self, client, session_id):
        first = self.chat(client, session_id, LOCKOUT_MSG)
        self.assertEqual(first["state"], "await_confirmation")
        return first["pending_action"]["action_id"]


class SharedSessionTests(Batch4Base):
    """SES-T2: two clients interleaving messages on ONE session id. The app has
    no notion of 'client': both requests are the same conversation."""

    def test_second_client_recall_supersedes_draft_and_reads_session_memory(self):
        app = self.make_app(*DRAFT_SCRIPT)
        with AuthedTestClient(app) as client_a, AuthedTestClient(app) as client_b:
            action_id = self.pending_draft(client_a, "ses-t2-shared")
            recall = self.chat(client_b, "ses-t2-shared", "What did I report and what have I tried?")
            # Code-derived outcome: recall answers from the stored session and
            # supersedes the pending action, with zero model calls.
            self.assertEqual(recall["state"], "recall")
            self.assertIn("I already checked saved passwords and found none.", recall["reply"])
            self.assertEqual(self.store.get_action(action_id)["status"], "superseded")
            late = client_a.post("/api/approve", json={
                "session_id": "ses-t2-shared", "action_id": action_id, "approved": True}).json()
            self.assertIn(ALREADY_USED, late["reply"])
        self.assertEqual(self.mcp.writes, [])
        self.assertEqual(len(self.runtime.script_calls), 3)  # the draft turn only
        # Interference documented honestly: client B invalidated client A's
        # pending approval AND read A's stored statements. The only thing B
        # needed was the session id - the known asserted-identity limitation.

    def test_second_client_new_topic_resets_first_clients_issue_context(self):
        app = self.make_app(*DRAFT_SCRIPT, {"action": "retrieve", "query": "printer"})
        with AuthedTestClient(app) as client_a, AuthedTestClient(app) as client_b:
            action_id = self.pending_draft(client_a, "ses-t2-reset")
            other = self.chat(client_b, "ses-t2-reset",
                              "Actually my printer shows error PRN-19 and will not print.")
            # Code-derived outcome: a distinct symptom/new error family resets
            # the issue; PRN-19 is undocumented in the scripted evidence, so
            # the turn ends in the deterministic 'unknown' offer.
            self.assertEqual(other["state"], "unknown")
            context = self.store.get_session("ses-t2-reset")
            self.assertIn("PRN-19", context["issue"])
            self.assertNotIn("locked", context["issue"])      # A's issue is GONE
            self.assertEqual(context["messages"],
                             ["Actually my printer shows error PRN-19 and will not print."])
            self.assertEqual(self.store.get_action(action_id)["status"], "superseded")
        self.assertEqual(self.mcp.writes, [])
        # Interference: B's unrelated problem replaced A's in-progress context
        # and invalidated A's pending approval. Within one conversation this is
        # the designed new-issue behaviour; across clients it is interference
        # enabled by the shareable, unauthenticated session id.

    def test_second_client_same_topic_message_blends_into_one_context(self):
        app = self.make_app(*DRAFT_SCRIPT, {"action": "retrieve", "query": "codes"},
                            dict(ANSWER), REVIEW_OK)
        with AuthedTestClient(app) as client_a, AuthedTestClient(app) as client_b:
            self.pending_draft(client_a, "ses-t2-blend")
            blended = self.chat(client_b, "ses-t2-blend", "I also cannot find my backup codes.")
            self.assertEqual(blended["state"], "answer")
            context = self.store.get_session("ses-t2-blend")
            # Code-derived outcome: same/unclassified topic appends; both
            # clients' messages now form ONE issue narrative.
            self.assertEqual(context["messages"],
                             [LOCKOUT_MSG, "I also cannot find my backup codes."])
            self.assertIn("locked three times", context["issue"])
            self.assertIn("backup codes", context["issue"])
            # Cross-client visibility reaches MODEL INPUT, not just storage:
            packets = [p for _, schema, p in self.runtime.script_calls if schema == "Candidate"]
            self.assertTrue(any("backup codes" in str(p.get("context")) and
                                "locked three times" in str(p.get("context")) for p in packets))
        self.assertEqual(self.mcp.writes, [])


class ApprovalRaceTests(Batch4Base):
    """APP-T3 sequential orderings; the interleaved pair is in the async class."""

    def test_reject_then_approve_writes_nothing(self):
        app = self.make_app(*DRAFT_SCRIPT)
        with AuthedTestClient(app) as client:
            action_id = self.pending_draft(client, "app-t3-rta")
            rejected = client.post("/api/approve", json={
                "session_id": "app-t3-rta", "action_id": action_id, "approved": False}).json()
            self.assertIn("Nothing was written", rejected["reply"])
            self.assertEqual(self.store.get_action(action_id)["status"], "rejected")
            approve = client.post("/api/approve", json={
                "session_id": "app-t3-rta", "action_id": action_id, "approved": True}).json()
            self.assertIsNone(approve["result"])
            self.assertIn(ALREADY_USED, approve["reply"])
        self.assertEqual(self.mcp.writes, [])

    def test_approve_then_reject_keeps_exactly_one_write(self):
        app = self.make_app(*DRAFT_SCRIPT)
        with AuthedTestClient(app) as client:
            action_id = self.pending_draft(client, "app-t3-atr")
            approved = client.post("/api/approve", json={
                "session_id": "app-t3-atr", "action_id": action_id, "approved": True}).json()
            self.assertEqual(approved["result"], {"ticket_id": "IT-2001"})
            late_reject = client.post("/api/approve", json={
                "session_id": "app-t3-atr", "action_id": action_id, "approved": False}).json()
            # storage.reject only transitions 'pending' rows, so this is a no-op:
            self.assertIn("unavailable or already used", late_reject["reply"])
            self.assertEqual(self.store.get_action(action_id)["status"], "succeeded")
        self.assertEqual(len(self.mcp.writes), 1)

    def _expire(self, action_id, delta_s: float):
        with self.store.connect() as db:
            db.execute("UPDATE actions SET expires=? WHERE id=?", (time.time() + delta_s, action_id))

    def test_expired_action_cannot_be_approved_or_reopened(self):
        app = self.make_app(*DRAFT_SCRIPT)
        with AuthedTestClient(app) as client:
            action_id = self.pending_draft(client, "app-t3-exp")
            self._expire(action_id, -1)
            approve = client.post("/api/approve", json={
                "session_id": "app-t3-exp", "action_id": action_id, "approved": True}).json()
            self.assertIsNone(approve["result"])
            self.assertIn(ALREADY_USED, approve["reply"])
            self.assertEqual(self.store.get_action(action_id)["status"], "expired")
            # reopen() only resurrects failed/unknown actions, never expired ones:
            self.assertIsNone(self.approvals.retry("app-t3-exp", action_id))
        self.assertEqual(self.mcp.writes, [])

    def test_approval_before_expiry_still_succeeds(self):
        app = self.make_app(*DRAFT_SCRIPT)
        with AuthedTestClient(app) as client:
            action_id = self.pending_draft(client, "app-t3-soon")
            self._expire(action_id, 30)  # close to expiry but still valid
            approved = client.post("/api/approve", json={
                "session_id": "app-t3-soon", "action_id": action_id, "approved": True}).json()
            self.assertEqual(approved["result"], {"ticket_id": "IT-2001"})
        self.assertEqual(len(self.mcp.writes), 1)

    def test_reject_of_time_expired_pending_row_is_a_benign_no_write(self):
        """Observed behaviour: reject() does not check the expiry timestamp, so
        a time-expired but still-'pending' row can be explicitly rejected.
        Benign either way - neither path writes - recorded, not a defect."""
        app = self.make_app(*DRAFT_SCRIPT)
        with AuthedTestClient(app) as client:
            action_id = self.pending_draft(client, "app-t3-expreject")
            self._expire(action_id, -1)
            rejected = client.post("/api/approve", json={
                "session_id": "app-t3-expreject", "action_id": action_id, "approved": False}).json()
            self.assertIn("Nothing was written", rejected["reply"])
            self.assertEqual(self.store.get_action(action_id)["status"], "rejected")
        self.assertEqual(self.mcp.writes, [])


class ConcurrentApproveRejectTests(unittest.IsolatedAsyncioTestCase):
    """APP-T3 interleaved pair: approve and reject fired concurrently. The
    outcome ORDER is not deterministic, so the assertions pin the invariant
    the code guarantees, whichever request wins the lock."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.store = Store(self.data / "state.sqlite3")
        self.mcp = DirectoryMCP()
        self.approvals = Approvals(self.store, self.mcp)

    async def test_concurrent_approve_and_reject_single_consistent_outcome(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}):
            runtime = ScriptedWorkflow(self.store, self.mcp, FakeRetrieval(), self.approvals,
                                       data_dir=self.data, script=DRAFT_SCRIPT)
        api = create_test_app(runtime)
        api.state.runtime = runtime  # ASGITransport does not run the lifespan
        transport = httpx.ASGITransport(app=api)
        async with AuthedAsyncClient(transport=transport, base_url="http://app.test") as client:
            first = (await client.post("/api/chat", json={
                "session_id": "app-t3-race", "message": LOCKOUT_MSG,
                "user": {"email": SARA["email"]}})).json()
            action_id = first["pending_action"]["action_id"]
            approve_response, reject_response = await asyncio.gather(
                client.post("/api/approve", json={"session_id": "app-t3-race",
                                                  "action_id": action_id, "approved": True}),
                client.post("/api/approve", json={"session_id": "app-t3-race",
                                                  "action_id": action_id, "approved": False}))
        approve, reject = approve_response.json(), reject_response.json()
        final = self.store.get_action(action_id)["status"]
        self.assertIn(final, {"succeeded", "rejected"})
        if final == "succeeded":   # approve won the lock
            self.assertEqual(approve["result"], {"ticket_id": "IT-2001"})
            self.assertIn("unavailable or already used", reject["reply"])
            self.assertEqual(len(self.mcp.writes), 1)
        else:                      # reject won the lock
            self.assertIsNone(approve["result"])
            self.assertIn(ALREADY_USED, approve["reply"])
            self.assertIn("Nothing was written", reject["reply"])
            self.assertEqual(self.mcp.writes, [])
        # Never both: a ticket result and a rejected action cannot coexist.
        self.assertFalse(approve["result"] and final == "rejected")


if __name__ == "__main__":
    unittest.main()
