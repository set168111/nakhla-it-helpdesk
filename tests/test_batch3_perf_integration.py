"""ISOLATED deterministic integration tests (batch 3: APP-T2, PERF-T1, PERF-T2).

Reuses the batch-2 harness: dedicated simulator subprocess on 127.0.0.1:8112,
real supplied MCP server (stdio child, venv interpreter), scripted model, fake
retrieval, temporary SQLite stores, OPENROUTER_API_KEY blanked everywhere.
Never contacts the running services on 7860/8000/8102.

Measurement scope, stated up front: the application intentionally serializes
/api/chat, /api/approve and /health behind one process-global asyncio lock in
a single worker. The PERF tests therefore measure SERIALIZED QUEUEING of an
in-process ASGI client (no network stack, no browser). They say nothing about
production capacity, internet bandwidth, or multi-worker safety - multi-worker
operation is unsupported and untested.

Opt-in: INTEGRATION_BATCH3=1 .venv/Scripts/python.exe -B -m unittest tests.test_batch3_perf_integration -v
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import statistics
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from app.approvals import Approvals
from tests.auth_helpers import AuthedAsyncClient, AuthedTestClient, create_test_app
from app.mcp_client import MCPClient
from app.storage import Store
from tests.test_agent_workflow import FakeRetrieval, ScriptedWorkflow
from tests.test_batch2_integration import (PAYLOAD, ROOT, SARA, SIM_PORT, SIM_URL, TEST_KEY,
                                           admin, created_tickets, port_free, start_simulator)

EVIDENCE = ROOT / "evidence" / "security-tests-2026-11" / "batch3-perf.json"
# Ten distinct requesters with archive tickets (owners verified from the dataset).
REQUESTERS = ["sara.mikhail@nakhla.example", "tariq.hamdan@nakhla.example",
              "noor.barakat@nakhla.example", "hiba.qasem@nakhla.example",
              "ahmad.yassin@nakhla.example", "omar.farah@nakhla.example",
              "salma.aziz@nakhla.example", "rana.khalil@nakhla.example",
              "reem.halabi@nakhla.example", "jad.khatib@nakhla.example"]


def owner_ticket_ids() -> dict[str, set[str]]:
    archive = json.loads((ROOT / "dataset" / "tickets" / "historical_tickets.json").read_text(encoding="utf-8"))
    owners: dict[str, set[str]] = {}
    for ticket in archive["tickets"]:
        owners.setdefault(ticket["requester_email"], set()).add(ticket["ticket_id"])
    return owners


def record_metrics(section: str, payload: dict):
    data = json.loads(EVIDENCE.read_text(encoding="utf-8")) if EVIDENCE.exists() else {}
    data[section] = payload
    EVIDENCE.write_text(json.dumps(data, indent=1), encoding="utf-8")


def percentile(latencies: list[float], fraction: float) -> float:
    ordered = sorted(latencies)
    return ordered[min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))]


@unittest.skipUnless(os.getenv("INTEGRATION_BATCH3") == "1",
                     "Opt in to the isolated-simulator batch 3 integration tests")
class Batch3IntegrationTests(unittest.IsolatedAsyncioTestCase):
    simulator: subprocess.Popen | None = None

    @classmethod
    def setUpClass(cls):
        if not port_free(SIM_PORT):
            raise unittest.SkipTest(f"Port {SIM_PORT} is busy; refusing to touch an existing service")
        cls.simulator = start_simulator()

    @classmethod
    def tearDownClass(cls):
        if cls.simulator:
            cls.simulator.terminate()
            cls.simulator.wait(timeout=15)
            cls.simulator = None

    def setUp(self):
        self.assertTrue(admin("POST", "/admin/reset").json()["ok"])
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.store = Store(self.data / "state.sqlite3")
        self.owners = owner_ticket_ids()

    def mcp_client(self) -> MCPClient:
        patcher = patch.dict(os.environ, {"HELPDESK_API_URL": SIM_URL,
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

    async def test_app_t2_idempotency_is_per_action_not_per_content(self):
        """APP-T2: identical payload content in two separately approved actions
        is action-level idempotency, not content deduplication - the same
        action replayed stays one ticket; a second approved action with the
        same content is a legitimate separate ticket."""
        async with self.mcp_client() as mcp:
            approvals = Approvals(self.store, mcp)
            first_action = approvals.propose("b3-app-t2-s1", PAYLOAD, SARA)
            second_action = approvals.propose("b3-app-t2-s2", PAYLOAD, SARA)
            self.assertNotEqual(first_action["action_id"], second_action["action_id"])
            self.assertEqual(first_action["payload"], second_action["payload"])  # same content
            first = await approvals.decide("b3-app-t2-s1", first_action["action_id"], True)
            replay = await approvals.decide("b3-app-t2-s1", first_action["action_id"], True)
            self.assertIsNone(replay["result"])
            self.assertEqual(created_tickets()["count"], 1)  # same action retried -> one ticket
            second = await approvals.decide("b3-app-t2-s2", second_action["action_id"], True)
        live = created_tickets()
        self.assertEqual(live["count"], 2)  # separately approved action -> separate ticket
        self.assertNotEqual(first["result"]["ticket_id"], second["result"]["ticket_id"])
        self.assertEqual({t["ticket_id"] for t in live["tickets"]},
                         {first["result"]["ticket_id"], second["result"]["ticket_id"]})
        log = admin("GET", "/admin/log", params={"limit": 500}).json()["entries"]
        creates = [e for e in log if e.get("operation") == "create_ticket" and e["method"] == "POST"]
        self.assertEqual(len(creates), 2)

    async def _stage(self, mcp, label: str, emails: list[str]) -> dict:
        """Run len(emails) concurrent /api/chat history turns through the real
        HTTP contract (in-process ASGI) and return stage metrics."""
        scripted, _ = self.workflow(mcp, *([{"action": "history"}] * len(emails)))
        api = create_test_app(scripted)
        api.state.runtime = scripted  # ASGITransport does not run the lifespan
        transport = httpx.ASGITransport(app=api)
        sessions = [f"b3-{label}-{i}" for i in range(len(emails))]
        batch_start = time.monotonic()

        async def one(session_id: str, email: str) -> dict:
            started = time.monotonic()
            response = await client.post("/api/chat", json={
                "session_id": session_id, "message": "Show my tickets.", "user": {"email": email}})
            return {"session": session_id, "email": email, "start": started,
                    "end": time.monotonic(), "status": response.status_code, "body": response.json()}

        async with AuthedAsyncClient(transport=transport, base_url="http://app.test", timeout=120) as client:
            results = await asyncio.gather(*(one(s, e) for s, e in zip(sessions, emails)))
        for result in results:
            body = result["body"]
            self.assertEqual(result["status"], 200)
            self.assertEqual(body["state"], "history", body["reply"])
            self.assertEqual(body["session_id"], result["session"])
            ids = set(re.findall(r"IT-\d{4}", body["reply"]))
            self.assertTrue(ids)
            self.assertLessEqual(ids, self.owners[result["email"]])
            context = self.store.get_session(result["session"])
            self.assertEqual(context["email"], result["email"])
            self.assertEqual(context["messages"], ["Show my tickets."])
        latencies = [r["end"] - r["start"] for r in results]
        completion = sorted(r["end"] for r in results)
        executions = [completion[0] - batch_start] + [b - a for a, b in zip(completion, completion[1:])]
        makespan = completion[-1] - batch_start
        return {"requests": len(emails),
                "latency_p50_s": round(percentile(latencies, 0.50), 3),
                "latency_p95_s": round(percentile(latencies, 0.95), 3),
                "latency_max_s": round(max(latencies), 3),
                "mean_execution_s": round(statistics.mean(executions), 3),
                "mean_queueing_s": round(statistics.mean(latencies) - statistics.mean(executions), 3),
                "makespan_s": round(makespan, 3),
                "throughput_rps": round(len(emails) / makespan, 2),
                "errors": 0}

    async def test_perf_t1_staged_serialized_concurrency(self):
        """PERF-T1: 2, 5 and 10 concurrent requests; same requester in separate
        sessions, and different requesters. All turns run the real MCP/simulator
        reads. The 'history' state assertion doubles as the SQLite-locking and
        dependency-error check: such failures surface as 'stopped'. Scope:
        serialized single-worker queueing over in-process transport."""
        stages: dict[str, dict] = {}
        async with self.mcp_client() as mcp:
            for count in (2, 5, 10):
                stages[f"same_requester_x{count}"] = await self._stage(
                    mcp, f"same{count}", [SARA["email"]] * count)
                stages[f"different_requesters_x{count}"] = await self._stage(
                    mcp, f"diff{count}", REQUESTERS[:count])
        for label, metrics in stages.items():
            self.assertEqual(metrics["errors"], 0, label)
        largest = stages["different_requesters_x10"]
        self.assertGreater(largest["latency_p95_s"], largest["mean_execution_s"] * 2)
        record_metrics("perf_t1_staged_concurrency", {
            "scope": "Serialized single-worker queueing via in-process ASGI; scripted model; "
                     "real MCP+simulator reads. NOT production capacity, NOT multi-worker safety.",
            "stages": stages})

    async def test_perf_t2_slow_turn_queues_chat_and_health_then_recovers(self):
        """PERF-T2: one controlled slow turn (simulator 'slow' fault, +3s on the
        first search) with another chat and /health behind it. Both queue behind
        the process-global lock and recover; nothing is changed in the app."""
        self.assertTrue(admin("POST", "/admin/faults",
                              json={"target": "search_tickets", "mode": "slow", "count": 1}).json()["ok"])
        try:
            async with self.mcp_client() as mcp:
                scripted, _ = self.workflow(mcp, {"action": "history"}, {"action": "history"})
                api = create_test_app(scripted)
                api.state.runtime = scripted
                transport = httpx.ASGITransport(app=api)
                async with AuthedAsyncClient(transport=transport, base_url="http://app.test",
                                             timeout=60) as client:
                    async def timed(name, factory):
                        started = time.monotonic()
                        response = await factory()
                        return {"name": name, "start": started, "end": time.monotonic(),
                                "status": response.status_code, "body": response.json()}

                    slow_task = asyncio.create_task(timed("slow_chat", lambda: client.post(
                        "/api/chat", json={"session_id": "b3-perf-t2-slow", "message": "Show my tickets.",
                                           "user": {"email": SARA["email"]}})))
                    await asyncio.sleep(0.4)  # let the slow turn take the lock first
                    fast_task = asyncio.create_task(timed("queued_chat", lambda: client.post(
                        "/api/chat", json={"session_id": "b3-perf-t2-fast", "message": "Show my tickets.",
                                           "user": {"email": "tariq.hamdan@nakhla.example"}})))
                    health_task = asyncio.create_task(timed("queued_health", lambda: client.get("/health")))
                    slow, fast, health = await asyncio.gather(slow_task, fast_task, health_task)
                    recovery_start = time.monotonic()
                    recovery = await client.get("/health")
                    recovery_s = time.monotonic() - recovery_start
        finally:
            admin("DELETE", "/admin/faults")
        for result in (slow, fast, health):
            self.assertEqual(result["status"], 200, result["name"])
        self.assertEqual(slow["body"]["state"], "history")
        self.assertEqual(fast["body"]["state"], "history")
        self.assertGreaterEqual(slow["end"] - slow["start"], 3.0)   # the fault really slowed it
        self.assertGreaterEqual(fast["end"], slow["end"] - 0.05)    # queued behind the lock
        self.assertGreaterEqual(health["end"], slow["end"] - 0.05)  # health queues too
        self.assertEqual(recovery.status_code, 200)
        self.assertLess(recovery_s, 2.5)                            # and it recovers
        record_metrics("perf_t2_slow_turn_queueing", {
            "scope": "Single controlled slow simulator read; chat and /health share the "
                     "process-global lock (documented docker-compose healthcheck caveat). "
                     "Not a capacity claim.",
            "slow_chat_s": round(slow["end"] - slow["start"], 3),
            "queued_chat_s": round(fast["end"] - fast["start"], 3),
            "queued_chat_wait_s": round(max(0.0, slow["end"] - fast["start"]), 3),
            "queued_health_s": round(health["end"] - health["start"], 3),
            "recovery_health_s": round(recovery_s, 3)})


if __name__ == "__main__":
    unittest.main()
