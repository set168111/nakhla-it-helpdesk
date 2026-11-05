"""ISOLATED deterministic integration tests (batch 2, 2026-11-02).

Real application code, the real supplied MCP server (stdio child started by
MCPClient with the venv interpreter) and a real, DEDICATED helpdesk simulator
subprocess on 127.0.0.1:8112 - never the running services on 7860/8000/8102.
Model responses are scripted and retrieval is fake; OPENROUTER_API_KEY is
blanked for every process this batch starts, so no external AI or embedding
call can occur. Temporary SQLite stores only; the real data/ directory and
spending ledgers are never read or written.

Identity remains ASSERTED, not authenticated. "Owner" below means the
directory record matching the asserted email, not a verified person.

The supplied simulator 'timeout' fault sleeps and then returns 504 BEFORE any
create logic: it is a genuine no-write failure. Response-loss AFTER a
successful write is therefore exercised through a test-only dropping proxy
(stdlib http.server) in front of the simulator; neither the simulator nor the
application is modified.

Opt-in (keeps ordinary offline runs service-free):
  INTEGRATION_BATCH2=1 .venv/Scripts/python.exe -B -m unittest tests.test_batch2_integration -v
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from app.approvals import Approvals
from tests.auth_helpers import AuthedAsyncClient, AuthedTestClient, claim_for, create_test_app
from app.mcp_client import MCPClient
from app.storage import Store
from tests.test_agent_workflow import CHUNK, FakeRetrieval, ScriptedWorkflow

ROOT = Path(__file__).resolve().parents[1]
SIM_PORT, PROXY_PORT = 8112, 8114
SIM_URL = f"http://127.0.0.1:{SIM_PORT}"
PROXY_URL = f"http://127.0.0.1:{PROXY_PORT}"
FORBIDDEN_PORTS = {7860, 8000, 8102}  # the running project; never contacted
TEST_KEY = "batch2-isolated-key"

SARA = {"email": "sara.mikhail@nakhla.example", "department": "Support", "vpn_gateway": "GW-1"}
OMAR = {"email": "omar.farah@nakhla.example", "department": "Sales", "vpn_gateway": "GW-2"}
SARA_ARCHIVE_ID = "IT-1021"    # sara.mikhail's own archive ticket (dataset-verified owner)
FOREIGN_TICKET_ID = "IT-1029"  # omar.farah's archive ticket with a poisoned description
FOREIGN_DETAILS = ("Wireshark", "always P1", "approvals are not needed")
LOCKOUT_MSG = ("My account locked three times today without a known cause. "
               "I already checked saved passwords and found none. Please open a ticket.")
DRAFT = {"intent": "draft", "subject": "Repeated unexplained lockouts", "description": LOCKOUT_MSG,
         "attempted_steps": ["I already checked saved passwords and found none."], "affected_users": 1,
         "claims": [{"text": "Three unexplained daily lockouts require Security Operations escalation at P2.",
                     "chunk_ids": [CHUNK["chunk_id"]]}]}
REVIEW_OK = {"accepted": True, "complete": True}
PAYLOAD = {"subject": "Repeated unexplained lockouts", "description": LOCKOUT_MSG,
           "category": "security", "priority": "P2", "requester_email": SARA["email"],
           "department": SARA["department"],
           "attempted_steps": ["I already checked saved passwords and found none."],
           "kb_refs": ["KB-006"], "affected_users": 1}


def port_free(port: int) -> bool:
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", port)) != 0


def wait_health(url: str, timeout: float = 45) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            response = httpx.get(url + "/health", timeout=2)
            if response.status_code == 200 and response.json().get("service") == "helpdesk":
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.4)
    return False


def start_simulator() -> subprocess.Popen:
    env = dict(os.environ)
    env.update({"HELPDESK_API_KEY": TEST_KEY,
                "HELPDESK_DATA_DIR": str(ROOT / "services" / "data"),
                "HELPDESK_DATASET_DIR": str(ROOT / "dataset"),
                "OPENROUTER_API_KEY": ""})
    process = subprocess.Popen(
        [sys.executable, "-B", "-m", "uvicorn", "services.helpdesk_api:app",
         "--host", "127.0.0.1", "--port", str(SIM_PORT), "--log-level", "warning"],
        cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not wait_health(SIM_URL):
        process.terminate()
        raise RuntimeError(f"Isolated simulator failed to start on {SIM_URL}")
    return process


def admin(method: str, path: str, **kwargs) -> httpx.Response:
    return httpx.request(method, SIM_URL + path, timeout=10, **kwargs)


def created_tickets() -> dict:
    return admin("GET", "/admin/tickets").json()


class DroppingProxyHandler(BaseHTTPRequestHandler):
    """Test-only pass-through proxy. While drop_remaining > 0, a POST to
    /api/tickets is forwarded (the upstream write really happens) and then the
    client connection is closed without a response: response loss AFTER a
    successful write. Everything else is relayed unchanged."""

    protocol_version = "HTTP/1.1"

    def _handle(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in {"host", "content-length", "connection", "accept-encoding"}}
        upstream = httpx.request(self.command, SIM_URL + self.path, content=body,
                                 headers=headers, timeout=30)
        if self.command == "POST" and self.path == "/api/tickets" and self.server.drop_remaining > 0:
            self.server.drop_remaining -= 1
            self.close_connection = True
            self.connection.close()
            return
        payload = upstream.content
        self.send_response(upstream.status_code)
        self.send_header("Content-Type", upstream.headers.get("content-type", "application/json"))
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = _handle
    do_POST = _handle

    def finish(self):
        try:
            super().finish()
        except OSError:
            pass  # expected after a deliberate connection drop

    def log_message(self, *args):
        pass


@unittest.skipUnless(os.getenv("INTEGRATION_BATCH2") == "1",
                     "Opt in to the isolated-simulator integration batch")
class IsolatedIntegrationTests(unittest.IsolatedAsyncioTestCase):
    simulator: subprocess.Popen | None = None

    @classmethod
    def setUpClass(cls):
        # Effective-target verification before anything executes: the batch may
        # only ever talk to the dedicated ports, which must start out free.
        assert SIM_PORT not in FORBIDDEN_PORTS and PROXY_PORT not in FORBIDDEN_PORTS
        assert SIM_URL.endswith(":8112") and PROXY_URL.endswith(":8114")
        if not (port_free(SIM_PORT) and port_free(PROXY_PORT)):
            raise unittest.SkipTest(
                f"Ports {SIM_PORT}/{PROXY_PORT} are busy; refusing to touch an existing service")
        cls.simulator = start_simulator()

    @classmethod
    def tearDownClass(cls):
        if cls.simulator:
            cls.simulator.terminate()
            cls.simulator.wait(timeout=15)
            cls.simulator = None

    @classmethod
    def restart_simulator(cls):
        cls.simulator.terminate()
        cls.simulator.wait(timeout=15)
        cls.simulator = start_simulator()

    def setUp(self):
        reset = admin("POST", "/admin/reset").json()
        self.assertTrue(reset["ok"])
        self.assertEqual(created_tickets()["count"], 0)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.store = Store(self.data / "state.sqlite3")

    def mcp_client(self, url: str = SIM_URL) -> MCPClient:
        """MCPClient copies os.environ when entered; point the supplied MCP
        server at the isolated target and blank the provider credential."""
        patcher = patch.dict(os.environ, {"HELPDESK_API_URL": url,
                                          "HELPDESK_API_KEY": TEST_KEY,
                                          "OPENROUTER_API_KEY": ""})
        patcher.start()
        self.addCleanup(patcher.stop)
        return MCPClient()

    def workflow(self, mcp, *script):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}):
            approvals = Approvals(self.store, mcp)
            scripted = ScriptedWorkflow(self.store, mcp, FakeRetrieval(), approvals,
                                        data_dir=self.data, script=script)
        return scripted, approvals

    async def test_own_t1_history_lists_only_requester_archive_tickets(self):
        """OWN-T1: real own-history works (actual records, not a leak-free
        clarification) and includes no other requester's tickets."""
        async with self.mcp_client() as mcp:
            scripted, _ = self.workflow(mcp, {"action": "history"})
            result = await scripted.chat("b2-own-t1", "Show my tickets.", {"email": SARA["email"]})
        self.assertEqual(result["state"], "history")
        ids = set(re.findall(r"IT-\d{4}", result["reply"]))
        self.assertEqual(ids, {SARA_ARCHIVE_ID})
        self.assertIn("NakhlaCRM sign-in fails", result["reply"])  # genuinely usable history
        # List requests are deterministic since the batch-5 fixes: no model call
        # happens at all, so no ticket data can reach model input on this path.
        self.assertEqual(scripted.script_calls, [])

    async def test_own_t3_foreign_ticket_id_discloses_no_details_anywhere(self):
        """OWN-T3: requesting another requester's known ticket ID leaks none of
        its details to the user reply, the model inputs, or the trace file."""
        async with self.mcp_client() as mcp:
            scripted, _ = self.workflow(mcp, {"action": "get_ticket", "ticket_id": FOREIGN_TICKET_ID})
            result = await scripted.chat("b2-own-t3", f"What is the status of ticket {FOREIGN_TICKET_ID}?",
                                         {"email": SARA["email"]})
        self.assertEqual(result["state"], "refused")
        self.assertIn("not available for your account", result["reply"])
        response_blob = json.dumps(result)
        model_blob = json.dumps(scripted.script_calls)
        trace_blob = (self.data / "traces.jsonl").read_text(encoding="utf-8")
        for detail in FOREIGN_DETAILS:
            self.assertNotIn(detail, response_blob)
            self.assertNotIn(detail, model_blob)
            self.assertNotIn(detail, trace_blob)
        self.assertEqual(len(scripted.script_calls), 1)  # ownership guard stopped the turn

    async def test_own_t3b_owner_can_still_read_their_own_ticket_by_id(self):
        """No over-refusal: the asserted owner's own ticket ID remains usable,
        and the poisoned description is not rendered."""
        async with self.mcp_client() as mcp:
            scripted, _ = self.workflow(mcp, {"action": "get_ticket", "ticket_id": FOREIGN_TICKET_ID})
            result = await scripted.chat("b2-own-t3b", f"What is the status of ticket {FOREIGN_TICKET_ID}?",
                                         {"email": OMAR["email"]})
        self.assertEqual(result["state"], "history")
        self.assertIn(FOREIGN_TICKET_ID, result["reply"])
        self.assertIn("(closed)", result["reply"])
        self.assertNotIn("approvals are not needed", result["reply"])

    async def test_ses_t7_simulator_restart_clears_created_tickets_truthfully(self):
        """SES-T7: after restarting only the isolated simulator, the created
        ticket is gone; the historical SQLite success is retained but is never
        presented as proof the ticket currently exists, and cannot be replayed."""
        async with self.mcp_client() as mcp:
            scripted, approvals = self.workflow(mcp, {"action": "retrieve", "query": "lockout"}, DRAFT, REVIEW_OK)
            first = await scripted.chat("b2-ses-t7", LOCKOUT_MSG, {"email": SARA["email"]})
            self.assertEqual(first["state"], "await_confirmation")
            action_id = first["pending_action"]["action_id"]
            approved = await approvals.decide("b2-ses-t7", action_id, True)
            ticket_id = approved["result"]["ticket_id"]
            live = created_tickets()
            self.assertEqual(live["count"], 1)
            self.assertEqual(live["tickets"][0]["requester_email"], SARA["email"])
        type(self).restart_simulator()
        self.assertEqual(created_tickets()["count"], 0)  # in-memory state cleared
        async with self.mcp_client() as mcp:
            scripted2, _ = self.workflow(mcp, {"action": "get_ticket", "ticket_id": ticket_id})
            result = await scripted2.chat("b2-ses-t7-after", f"What is the status of ticket {ticket_id}?",
                                          {"email": SARA["email"]})
            self.assertEqual(result["state"], "refused")
            self.assertNotIn(ticket_id, result["reply"])
            # Identical non-disclosing wording: nothing claims the ticket exists.
            self.assertIn("not available for your account", result["reply"])
            # The action history still says succeeded (truthful record of the
            # past write), but a retry cannot reuse it for a new write:
            self.assertEqual(self.store.get_action(action_id)["status"], "succeeded")
            retry = await scripted2.chat("b2-ses-t7", "retry", {"email": SARA["email"]})
            self.assertIn("no failed or uncertain draft", retry["reply"])
        self.assertEqual(created_tickets()["count"], 0)

    async def test_app_t1_concurrent_http_approvals_create_exactly_one_ticket(self):
        """APP-T1: two simultaneous HTTP approvals of the SAME action produce
        one ticket. NOTE: the single worker serializes requests behind a
        process-global lock, so this validates serialized double-approval,
        not multi-worker parallelism."""
        async with self.mcp_client() as mcp:
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}):
                approvals = Approvals(self.store, mcp)
            pending = approvals.propose("b2-app-t1", PAYLOAD, SARA)
            runtime = SimpleNamespace(approvals=approvals, retrieval=SimpleNamespace(ready=True),
                                      client=object(), mcp=mcp)
            api = create_test_app(runtime)
            api.state.runtime = runtime  # ASGITransport does not run the lifespan
            claim_for(api, "b2-app-t1", SARA["email"])  # the draft was proposed directly: the signed-in owner claims its session
            transport = httpx.ASGITransport(app=api)
            body = {"session_id": "b2-app-t1", "action_id": pending["action_id"], "approved": True}
            async with AuthedAsyncClient(transport=transport, base_url="http://app.test") as client:
                first, second = await asyncio.gather(client.post("/api/approve", json=body),
                                                     client.post("/api/approve", json=body))
        self.assertEqual({first.status_code, second.status_code}, {200})
        winner, loser = sorted([first.json(), second.json()], key=lambda d: d["result"] is None)
        self.assertRegex(winner["result"]["ticket_id"], r"^IT-\d{4}$")
        self.assertIsNone(loser["result"])
        self.assertIn("No new write was sent", loser["reply"])
        live = created_tickets()
        self.assertEqual(live["count"], 1)
        self.assertEqual(live["tickets"][0]["ticket_id"], winner["result"]["ticket_id"])
        log = admin("GET", "/admin/log", params={"limit": 200}).json()["entries"]
        creates = [e for e in log if e.get("operation") == "create_ticket" and e["method"] == "POST"]
        self.assertEqual(len(creates), 1)
        self.assertEqual(self.store.get_action(pending["action_id"])["status"], "succeeded")

    async def test_app_t6a_supplied_timeout_fault_is_no_write_and_retry_reuses_key(self):
        """APP-T6 part 1, supplied fault only: the simulator 'timeout' fault
        waits and returns 504 WITHOUT creating anything, so this exercises an
        uncertain outcome where no write landed - NOT response loss after a
        successful write. The retry reuses the same action id (= idempotency
        key) and exactly one ticket exists at the end."""
        arm = admin("POST", "/admin/faults", json={"target": "create_ticket", "mode": "timeout", "count": 1}).json()
        self.assertTrue(arm["ok"])
        try:
            async with self.mcp_client() as mcp:
                approvals = Approvals(self.store, mcp)
                pending = approvals.propose("b2-app-t6a", PAYLOAD, SARA)
                action_id = pending["action_id"]
                first = await approvals.decide("b2-app-t6a", action_id, True)
                self.assertIsNone(first["result"])
                self.assertIn("unknown", first["reply"])
                self.assertEqual(self.store.get_action(action_id)["status"], "unknown")
                self.assertEqual(created_tickets()["count"], 0)  # fault semantics: nothing was written
                admin("DELETE", "/admin/faults")
                reopened = approvals.retry("b2-app-t6a", action_id)
                self.assertEqual(reopened["action_id"], action_id)
                self.assertEqual(reopened["payload"], pending["payload"])
                second = await approvals.decide("b2-app-t6a", action_id, True)
                self.assertRegex(second["result"]["ticket_id"], r"^IT-\d{4}$")
                self.assertEqual(created_tickets()["count"], 1)
                self.assertEqual(self.store.get_action(action_id)["status"], "succeeded")
                await asyncio.sleep(8)  # let the faulted request finish server-side
                self.assertEqual(created_tickets()["count"], 1)  # the delayed 504 created nothing
        finally:
            admin("DELETE", "/admin/faults")

    async def test_app_t6b_response_lost_after_real_write_recovers_without_duplicate(self):
        """APP-T6 part 2, test-only proxy: the create request reaches the
        simulator and the ticket IS created, but the response is lost. The app
        records unknown (never claims success), and the retry with the SAME
        action id is answered by the simulator's idempotency replay: two POSTs,
        one ticket."""
        proxy = ThreadingHTTPServer(("127.0.0.1", PROXY_PORT), DroppingProxyHandler)
        proxy.drop_remaining = 1
        proxy.daemon_threads = True
        thread = threading.Thread(target=proxy.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(proxy.server_close)
        self.addCleanup(proxy.shutdown)
        async with self.mcp_client(url=PROXY_URL) as mcp:
            approvals = Approvals(self.store, mcp)
            pending = approvals.propose("b2-app-t6b", PAYLOAD, SARA)
            action_id = pending["action_id"]
            first = await approvals.decide("b2-app-t6b", action_id, True)
            self.assertIsNone(first["result"])  # the app never claims an unconfirmed success
            self.assertEqual(self.store.get_action(action_id)["status"], "unknown")
            live = created_tickets()
            self.assertEqual(live["count"], 1)  # ...but the write really landed
            created_id = live["tickets"][0]["ticket_id"]
            reopened = approvals.retry("b2-app-t6b", action_id)
            self.assertEqual(reopened["action_id"], action_id)  # same idempotency key
            second = await approvals.decide("b2-app-t6b", action_id, True)
            self.assertEqual(second["result"]["ticket_id"], created_id)  # replayed, not duplicated
        self.assertEqual(created_tickets()["count"], 1)
        log = admin("GET", "/admin/log", params={"limit": 500}).json()["entries"]
        creates = [e for e in log if e.get("operation") == "create_ticket" and e["method"] == "POST"]
        self.assertEqual(len(creates), 2)  # two POSTs with one ticket: idempotent replay
        self.assertEqual({e["status"] for e in creates}, {201})
        self.assertEqual(self.store.get_action(action_id)["status"], "succeeded")


if __name__ == "__main__":
    unittest.main()
