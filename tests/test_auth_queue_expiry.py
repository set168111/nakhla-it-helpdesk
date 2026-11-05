"""Offline regression: queued chat/approval must not survive logout or expiry."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import yaml

from app.auth import AuthService
from app.main import create_app


class QueuedAuthenticationTests(unittest.IsolatedAsyncioTestCase):
    def test_demo_ports_do_not_publish_simulator_or_network_login(self):
        root = Path(__file__).resolve().parents[1]
        services = yaml.safe_load((root / "docker-compose.yml").read_text())["services"]
        self.assertFalse(services["helpdesk-api"].get("ports"))
        self.assertEqual(services["app"]["ports"], ["127.0.0.1:8000:8000"])
        self.assertEqual(services["ui"]["ports"], ["127.0.0.1:7860:7860"])

    async def test_queued_chat_and_approval_recheck_logout_and_expiry(self):
        for endpoint in ("chat", "approve"):
            for end in ("logout", "expiry"):
                with self.subTest(endpoint=endpoint, end=end), tempfile.TemporaryDirectory() as tmp:
                    now = [1000.0]
                    auth = AuthService(Path(tmp) / "auth.sqlite3", clock=lambda: now[0], absolute_ttl=10)
                    auth.provision_employee("E-1", "sara.mikhail@nakhla.example", "Sara", "Support")
                    auth.set_password("E-1", "demo", "temporary-password")
                    token = auth.login("sara.mikhail@nakhla.example", "temporary-password")[0]
                    auth.claim_session("owned", "E-1")
                    entered, release, queued = asyncio.Event(), asyncio.Event(), asyncio.Event()

                    class Runtime:
                        calls = 0
                        decisions = 0

                        async def chat(self, *args):
                            self.calls += 1
                            entered.set()
                            await release.wait()
                            return {"reply": "done"}

                        async def decide(self, *args):
                            self.decisions += 1
                            return {"reply": "should not run"}

                    runtime = Runtime()
                    runtime.approvals = runtime
                    app = create_app(runtime, auth)
                    app.state.runtime = runtime
                    headers = {"Authorization": "Bearer " + token}
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
                        first = asyncio.create_task(client.post("/api/chat", headers=headers,
                                                   json={"session_id": "owned", "message": "hold"}))
                        await asyncio.wait_for(entered.wait(), 3)
                        original = auth.authenticate

                        def observe(value):
                            result = original(value)
                            queued.set()
                            return result

                        body = ({"session_id": "owned", "message": "recall"} if endpoint == "chat" else
                                {"session_id": "owned", "action_id": "draft", "approved": True})
                        with patch.object(auth, "authenticate", side_effect=observe):
                            second = asyncio.create_task(client.post("/api/" + endpoint, headers=headers, json=body))
                            try:
                                await asyncio.wait_for(queued.wait(), 3)
                                if end == "logout":
                                    self.assertEqual((await client.post("/api/logout", headers=headers)).status_code, 200)
                                else:
                                    now[0] += 11
                            finally:
                                release.set()
                            self.assertEqual((await asyncio.wait_for(second, 3)).status_code, 401)
                            self.assertEqual((await first).status_code, 200)
                    self.assertEqual(runtime.calls, 1)
                    self.assertEqual(runtime.decisions, 0)
