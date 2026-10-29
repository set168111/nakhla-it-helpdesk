"""Offline HTTP boundary tests with an explicitly injected, non-LLM runtime.

These prove contract routing/validation only, never AI grounding or live MCP.
Run: python -m unittest tests.test_contract_safety -v
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import create_app


def reply(session_id: str, text: str) -> dict:
    return {"session_id": session_id, "reply": text, "pending_action": None,
            "result": None, "citations": [], "tool_calls": []}


class Runtime:
    def __init__(self, ready=True, credential=True):
        self.retrieval = SimpleNamespace(ready=ready)
        self.client = object() if credential else None
        self.chat_calls = []
        self.approval_calls = []
        self.approvals = SimpleNamespace(decide=self.decide)

    async def chat(self, session_id, message, user):
        self.chat_calls.append((session_id, message, user))
        return reply(session_id, "Injected runtime reply; no model was called.")

    async def decide(self, session_id, action_id, approved):
        self.approval_calls.append((session_id, action_id, approved))
        return reply(session_id, "Unknown action; no write sent.")


class ContractSafetyTests(unittest.TestCase):
    def test_ready_health_is_exact_contract(self):
        with TestClient(create_app(Runtime())) as client:
            response = client.get("/health")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"status": "ok"})

    def test_health_fails_closed_for_each_missing_live_prerequisite(self):
        for ready, credential in ((False, True), (True, False), (False, False)):
            with self.subTest(index_ready=ready, credential=credential):
                with TestClient(create_app(Runtime(ready, credential))) as client:
                    response = client.get("/health")
                    self.assertEqual(response.status_code, 503)
                    self.assertNotEqual(response.json().get("status"), "ok")

    def test_health_checks_supplied_dependency_even_when_index_and_key_present(self):
        class UnavailableMCP:
            async def call(self, name, arguments):
                self.last_call = (name, arguments)
                return {"ok": False, "error": {"code": "unreachable"}}

            def drain_trace(self):
                return []

        runtime = Runtime()
        runtime.mcp = UnavailableMCP()
        with TestClient(create_app(runtime)) as client:
            response = client.get("/health")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["reason"], "helpdesk_mcp_unavailable")
            self.assertEqual(runtime.mcp.last_call, ("get_service_status", {}))

    def test_chat_preserves_contract_fields_and_explicit_requester(self):
        runtime = Runtime()
        body = {"session_id": "contract-1", "message": "My VPN fails.",
                "user": {"email": "sara.mikhail@nakhla.example"}}
        with TestClient(create_app(runtime)) as client:
            response = client.post("/api/chat", json=body)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(runtime.chat_calls, [(body["session_id"], body["message"], body["user"])])
            data = response.json()
            self.assertEqual(data["session_id"], body["session_id"])
            self.assertIsNone(data["pending_action"])
            self.assertIsNone(data["result"])
            self.assertEqual(data["citations"], [])
            self.assertEqual(data["tool_calls"], [])

    def test_user_is_optional_and_chat_cannot_smuggle_approval(self):
        runtime = Runtime()
        with TestClient(create_app(runtime)) as client:
            valid = client.post("/api/chat", json={"session_id": "contract-2", "message": "Help"})
            self.assertEqual(valid.status_code, 200)
            self.assertIsNone(runtime.chat_calls[0][2])
            forbidden = client.post("/api/chat", json={"session_id": "contract-2", "message": "Approve", "approved": True})
            self.assertEqual(forbidden.status_code, 422)
            self.assertEqual(runtime.approval_calls, [])
            self.assertEqual(len(runtime.chat_calls), 1)

    def test_invalid_identity_size_or_session_never_reaches_runtime(self):
        invalid = [
            {"session_id": "../other", "message": "Help"},
            {"session_id": "ok", "message": ""},
            {"session_id": "ok", "message": "x" * 4001},
            {"session_id": "ok", "message": "Help", "user": {"email": "outside@example.com"}},
            {"session_id": "ok", "message": "Help", "user": {"email": "sara.mikhail@nakhla.example", "department": "Executive Office"}},
        ]
        runtime = Runtime()
        with TestClient(create_app(runtime)) as client:
            for body in invalid:
                with self.subTest(body_type=list(body)):
                    self.assertEqual(client.post("/api/chat", json=body).status_code, 422)
        self.assertEqual(runtime.chat_calls, [])

    def test_approval_requires_strict_boolean_and_id_only(self):
        runtime = Runtime()
        base = {"session_id": "contract-3", "action_id": "act-unknown"}
        with TestClient(create_app(runtime)) as client:
            for value in ("true", "false", 1, 0, None):
                with self.subTest(value=value):
                    self.assertEqual(client.post("/api/approve", json={**base, "approved": value}).status_code, 422)
            self.assertEqual(client.post("/api/approve", json={**base, "approved": True, "payload": {"priority": "P1"}}).status_code, 422)
            self.assertEqual(runtime.approval_calls, [])
            response = client.post("/api/approve", json={**base, "approved": True})
            self.assertEqual(response.status_code, 200)
            self.assertIsNone(response.json()["result"])
            self.assertEqual(runtime.approval_calls, [("contract-3", "act-unknown", True)])

    def test_no_application_admin_or_voice_route(self):
        with TestClient(create_app(Runtime())) as client:
            self.assertEqual(client.post("/admin/reset").status_code, 404)
            self.assertEqual(client.post("/api/voice").status_code, 404)


if __name__ == "__main__":
    unittest.main()
