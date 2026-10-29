"""Focused approval invariants; local fake system exercises failures without LLM calls."""
import asyncio
import copy
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from app.approvals import Approvals, IMMEDIATE_ESCALATION
from app.mcp_client import MCPClient
from app.storage import Store


EMPLOYEE = {"email": "fadi.mansour@nakhla.example", "department": "Finance", "vpn_gateway": "GW-3"}
PAYLOAD = {"subject": "NakhlaConnect NX-403 remote access", "description": "NakhlaConnect shows NX-403 when connecting from home.",
           "category": "security", "priority": "P2", "requester_email": EMPLOYEE["email"], "department": "Finance",
           "attempted_steps": [IMMEDIATE_ESCALATION], "kb_refs": ["KB-016"], "affected_users": 1}


class FakeMCP:
    def __init__(self):
        self.employee = copy.deepcopy(EMPLOYEE)
        self.writes = []
        self.trace = []
        self.result = {"ok": True, "ticket": {"ticket_id": "IT-2001"}}
        self.directory_ok = True
        self.status = {"incidents": []}

    async def call(self, name, arguments):
        self.trace.append({"tool": name, "ok": True, "ms": 1})
        return ({"ok": self.directory_ok, "employee": self.employee} if name == "lookup_employee"
                else {"ok": True, "status": copy.deepcopy(self.status)})

    async def create_approved_ticket(self, payload, action_id):
        self.trace.append({"tool": "create_ticket", "ok": self.result.get("ok", False), "ms": 1})
        self.writes.append((copy.deepcopy(payload), action_id))
        await asyncio.sleep(0)
        return self.result

    def drain_trace(self):
        trace, self.trace = self.trace, []
        return trace


class ApprovalTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "state.sqlite3"
        self.store = Store(self.path)
        self.mcp = FakeMCP()
        self.approvals = Approvals(self.store, self.mcp)

    def draft(self):
        return self.approvals.propose("s", PAYLOAD, EMPLOYEE)

    def incident_draft(self):
        employee = {**EMPLOYEE, "department": "Support", "vpn_gateway": "GW-2"}
        self.mcp.employee = employee
        payload = {**PAYLOAD, "subject": "VPN NX-503 unavailable", "description": "VPN NX-503 fails.",
                   "department": "Support", "category": "network_access", "kb_refs": ["KB-002"]}
        return self.approvals.propose("s", payload, employee)

    def activate_incident(self):
        self.mcp.status = {"incidents": [{"id": "INC-2207", "status": "active", "service": "vpn",
            "error_codes": ["NX-503"], "affected": "GW-2", "workaround": "Use GW-1",
            "instructions": "Subscribe on the status page"}]}

    async def test_incident_activated_after_draft_supersedes_without_write(self):
        draft = self.incident_draft()
        self.activate_incident()
        reply = await self.approvals.decide("s", draft["action_id"], True)
        self.assertEqual(self.store.get_action(draft["action_id"])["status"], "superseded")
        self.assertIn("INC-2207", reply["reply"])
        self.assertIn("No individual ticket was created", reply["reply"])
        self.assertIsNone(reply["result"])
        await self.approvals.decide("s", draft["action_id"], True)
        self.assertIsNone(self.approvals.retry("s", draft["action_id"]))
        self.assertEqual(self.mcp.writes, [])

    async def test_incident_during_unknown_recovery_preserves_duplicate_write_guard(self):
        draft = self.incident_draft()
        action = draft["action_id"]
        self.mcp.result = {"ok": False, "error": {"code": "timeout"}}
        await self.approvals.decide("s", action, True)
        original = self.store.get_action(action)
        self.approvals.retry("s", action)
        self.activate_incident()
        reply = await self.approvals.decide("s", action, True)
        self.assertEqual(self.store.get_action(action)["status"], "unknown")
        self.assertEqual(reply["state"], "unknown")
        self.assertIn("INC-2207", reply["reply"])
        self.assertNotIn("No individual ticket was created", reply["reply"])
        self.assertIsNone(reply["result"])
        self.assertEqual(len(self.mcp.writes), 1)  # only the earlier uncertain attempt
        self.store.supersede("s")
        with self.assertRaises(ValueError):
            self.incident_draft()
        retry = self.approvals.retry("s", action)
        self.assertEqual(retry["payload"], original["payload"])
        self.assertEqual(self.store.get_action(action)["payload_hash"], original["payload_hash"])
        self.mcp.status = {"incidents": []}
        self.mcp.result = {"ok": True, "ticket": {"ticket_id": "IT-2001"}}
        await self.approvals.decide("s", action, True)
        await self.approvals.decide("s", action, True)
        self.assertEqual(self.mcp.writes[0], self.mcp.writes[1])
        self.assertEqual(len(self.mcp.writes), 2)  # reconciliation uses the same key

    async def test_schema_truthful_immediate_entry_and_exact_commit(self):
        draft = self.draft()
        reply = await self.approvals.decide("s", draft["action_id"], True)
        self.assertEqual(reply["result"], {"ticket_id": "IT-2001"})
        self.assertEqual(self.mcp.writes, [(PAYLOAD, draft["action_id"])])
        self.assertIn(IMMEDIATE_ESCALATION, draft["summary"])

    async def test_concurrent_double_approval_one_write(self):
        action = self.draft()["action_id"]
        replies = await asyncio.gather(*[self.approvals.decide("s", action, True) for _ in range(2)])
        self.assertEqual(len(self.mcp.writes), 1)
        self.assertEqual(sum(bool(r["result"]) for r in replies), 1)

    async def test_reject_unknown_cross_session_and_replay_no_write(self):
        action = self.draft()["action_id"]
        for session, identity in (("other", action), ("s", "missing")):
            self.assertIsNone((await self.approvals.decide(session, identity, True))["result"])
        await self.approvals.decide("s", action, False)
        await self.approvals.decide("s", action, True)
        self.assertFalse(self.mcp.writes)

    async def test_changed_draft_supersedes(self):
        first = self.draft()
        second = self.draft()
        await self.approvals.decide("s", first["action_id"], True)
        self.assertFalse(self.mcp.writes)
        self.assertEqual(self.store.get_action(second["action_id"])["status"], "pending")

    async def test_expired_draft_cannot_commit(self):
        action = self.store.propose("s", PAYLOAD, ttl=-1)
        await self.approvals.decide("s", action["action_id"], True)
        self.assertFalse(self.mcp.writes)
        self.assertEqual(self.store.get_action(action["action_id"])["status"], "expired")

    async def test_unknown_retry_retains_payload_and_key(self):
        action = self.draft()["action_id"]
        self.mcp.result = {"ok": False, "error": {"code": "timeout"}}
        reply = await self.approvals.decide("s", action, True)
        self.assertIn("unknown", reply["reply"])
        self.assertIsNone(reply["result"])
        retry = self.approvals.retry("s", action)
        self.assertEqual(retry["action_id"], action)
        self.assertEqual(retry["payload"], PAYLOAD)
        self.mcp.result = {"ok": True, "ticket": {"ticket_id": "IT-2001"}}
        await self.approvals.decide("s", action, True)
        self.assertEqual(self.mcp.writes[0], self.mcp.writes[1])

    async def test_503_no_automatic_retry(self):
        action = self.draft()["action_id"]
        self.mcp.result = {"ok": False, "error": {"code": "service_unavailable", "http_status": 503}}
        reply = await self.approvals.decide("s", action, True)
        self.assertIsNone(reply["result"])
        self.assertEqual(len(self.mcp.writes), 1)
        self.assertEqual(self.store.get_action(action)["status"], "failed")

    async def test_directory_change_blocks_write(self):
        action = self.draft()["action_id"]
        self.mcp.employee["department"] = "HR"
        await self.approvals.decide("s", action, True)
        self.assertFalse(self.mcp.writes)

    async def test_directory_unavailable_blocks_write(self):
        action = self.draft()["action_id"]
        self.mcp.directory_ok = False
        await self.approvals.decide("s", action, True)
        self.assertFalse(self.mcp.writes)

    async def test_restart_session_and_unknown_recovery(self):
        self.store.save_session("s", {"requester_email": EMPLOYEE["email"], "error_code": "NX-403"})
        action = self.draft()["action_id"]
        self.store.claim("s", action)
        restarted = Store(self.path)
        restarted.recover_interrupted()
        self.assertEqual(restarted.get_session("s")["error_code"], "NX-403")
        self.assertEqual(restarted.get_action(action)["status"], "unknown")
        with self.assertRaises(ValueError):
            restarted.propose("s", PAYLOAD)
        retry = restarted.reopen("s", action)
        self.assertEqual(retry["status"], "pending_recovery")
        restarted.supersede("s")
        self.assertEqual(restarted.get_action(action)["status"], "pending_recovery")
        with self.assertRaises(ValueError):
            restarted.propose("s", PAYLOAD)

    async def test_payload_tampering_cannot_commit(self):
        action = self.draft()["action_id"]
        changed = copy.deepcopy(PAYLOAD)
        changed["subject"] = "Tampered draft different from approved one"
        with self.store.connect() as db:
            db.execute("UPDATE actions SET payload=? WHERE id=?", (json.dumps(changed), action))
        await self.approvals.decide("s", action, True)
        self.assertFalse(self.mcp.writes)
        self.assertEqual(self.store.get_action(action)["status"], "invalid")

    async def test_unknown_retry_changed_evidence_retains_unknown(self):
        action = self.draft()["action_id"]
        self.mcp.result = {"ok": False, "error": {"code": "timeout"}}
        await self.approvals.decide("s", action, True)
        self.approvals.retry("s", action)
        self.approvals.current_fingerprint = lambda: "new-corpus"
        reply = await self.approvals.decide("s", action, True)
        self.assertIsNone(reply["result"])
        self.assertEqual(self.store.get_action(action)["status"], "unknown")
        with self.assertRaises(ValueError):
            self.draft()

    async def test_read_dispatch_cannot_call_writes(self):
        client = MCPClient()
        for name in ("create_ticket", "add_ticket_note", "admin/reset"):
            with self.assertRaises(PermissionError):
                await client.call(name, {})

    async def test_non_boolean_approval_no_write(self):
        action = self.draft()["action_id"]
        await self.approvals.decide("s", action, "true")
        self.assertFalse(self.mcp.writes)

    async def test_retention_removes_only_old_resolved_history(self):
        old = time.time() - 8 * 86400
        retained = {}
        for status in ("committing", "unknown", "pending_recovery", "pending", "failed"):
            session = "retain-" + status
            self.store.save_session(session, {"error_code": "NX-403"})
            action = self.store.propose(session, PAYLOAD)
            retained[session] = action["action_id"]
            with self.store.connect() as db:
                db.execute("UPDATE actions SET status=?,created=? WHERE id=?", (status, old, action["action_id"]))
                db.execute("UPDATE sessions SET updated=? WHERE id=?", (old, session))
        for status in ("succeeded", "rejected", "superseded", "invalid", "expired"):
            session = "delete-" + status
            self.store.save_session(session, {"error_code": "NX-403"})
            action = self.store.propose(session, PAYLOAD)
            with self.store.connect() as db:
                db.execute("UPDATE actions SET status=?,created=? WHERE id=?", (status, old, action["action_id"]))
                db.execute("UPDATE sessions SET updated=? WHERE id=?", (old, session))
        self.store.save_session("recent", {"error_code": "NX-403"})
        result = self.store.purge_history(days=7)
        self.assertEqual(result, {"sessions_deleted": 5, "actions_deleted": 5})
        for session, action in retained.items():
            self.assertIsNotNone(self.store.get_session(session))
            self.assertIsNotNone(self.store.get_action(action))
        self.assertIsNotNone(self.store.get_session("recent"))

    @unittest.skipUnless(os.getenv("LIVE_FAILURE_TEST") == "1", "Opt in to a single local simulator create-ticket fault")
    async def test_live_503_same_key_recovery(self):
        from dotenv import load_dotenv
        import httpx
        load_dotenv()
        api = (os.getenv("HELPDESK_API_URL") or "http://localhost:8102").rstrip("/")
        self.assertTrue(api.startswith(("http://localhost:", "http://127.0.0.1:")), "Fault test must target local simulator")
        async with httpx.AsyncClient(base_url=api) as harness:
            arm = await harness.post("/admin/faults", json={"target": "create_ticket", "mode": "error_503", "count": 1})
            arm.raise_for_status()
            async with MCPClient() as client:
                approvals = Approvals(self.store, client)
                draft = approvals.propose("live-failure", PAYLOAD, EMPLOYEE)
                before = await approvals.decide("live-failure", draft["action_id"], True)
                self.assertIsNone(before["result"])
                self.assertEqual(self.store.get_action(draft["action_id"])["status"], "failed")
                retry = approvals.retry("live-failure", draft["action_id"])
                self.assertEqual(retry["action_id"], draft["action_id"])
                self.assertEqual(retry["payload"], draft["payload"])
                after = await approvals.decide("live-failure", retry["action_id"], True)
                self.assertIsNotNone(after["result"], after["reply"])
                replay = await approvals.decide("live-failure", retry["action_id"], True)
                self.assertIsNone(replay["result"])
                self.assertFalse(replay["tool_calls"])
                evidence_dir = Path(__file__).resolve().parent.parent / "evidence"
                evidence_dir.mkdir(exist_ok=True)
                (evidence_dir / "failure-before-after.json").write_text(json.dumps({
                    "classification": "Observed deliberately injected local simulator transient 503; recovery-path validation, not an observed application code defect or model failure",
                    "fault": {"target": "create_ticket", "mode": "error_503", "count": 1},
                    "action_id": draft["action_id"], "same_key_and_payload_verified": True,
                    "before": before, "after": after, "replay": replay,
                    "actual_external_provider_cost_usd": 0,
                }, indent=2), encoding="utf-8")

    @unittest.skipUnless(os.getenv("LIVE_KIT_TEST") == "1", "Opt in to a local simulator write; no external provider")
    async def test_live_schema_api_accepts_truthful_immediate_escalation(self):
        from dotenv import load_dotenv
        load_dotenv()
        async with MCPClient() as client:
            approvals = Approvals(self.store, client)
            draft = approvals.propose("live-truthful", PAYLOAD, EMPLOYEE)
            result = await approvals.decide("live-truthful", draft["action_id"], True)
            self.assertIsNotNone(result["result"], result["reply"])
            ticket_id = result["result"]["ticket_id"]
            stored = await client.call("get_ticket", {"ticket_id": ticket_id})
            self.assertTrue(stored["ok"])
            self.assertEqual(stored["ticket"]["attempted_steps"], [IMMEDIATE_ESCALATION])
            self.assertEqual(stored["ticket"]["category"], "security")
            self.assertEqual(stored["ticket"]["assigned_team"], "Security Operations")
            evidence_dir = Path(__file__).resolve().parent.parent / "evidence"
            evidence_dir.mkdir(exist_ok=True)
            (evidence_dir / "immediate-escalation.json").write_text(json.dumps({
                "test": "unchanged schema and simulator API, real supplied MCP stdio",
                "payload": PAYLOAD, "action_id": draft["action_id"],
                "returned_ticket_id": ticket_id,
                "stored_attempted_steps": stored["ticket"]["attempted_steps"],
                "assigned_team": stored["ticket"]["assigned_team"],
                "external_provider_calls": 0,
            }, indent=2), encoding="utf-8")
            print("Live unchanged schema/API accepted truthful immediate escalation:", ticket_id)


if __name__ == "__main__":
    unittest.main()
