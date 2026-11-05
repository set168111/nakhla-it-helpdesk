"""OFFLINE tests for the authenticated eval runner (evals/run_evals.py, local change for the login batch).

The runner is exercised against the real create_app wiring through a TestClient (an httpx.Client), with a stub
runtime and a throwaway credentials file. No model, no simulator. Original case inputs are not modified.

Run: python -B -m unittest tests.test_eval_runner_auth -v
"""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.auth import AuthService
from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("run_evals_under_test", ROOT / "evals" / "run_evals.py")
run_evals = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_evals)

EMAIL, PASSWORD = "sara.mikhail@nakhla.example", "eval-only-password-Z9"


class StubRuntime:
    retrieval = type("R", (), {"ready": True})()
    client = object()

    def __init__(self):
        self.approvals, self.users = self, []

    async def chat(self, session_id, message, user):
        self.users.append(user)
        return {"session_id": session_id, "reply": f"stub answer for {user['email']}", "state": "answered",
                "pending_action": None, "result": None, "citations": [], "tool_calls": []}

    async def decide(self, session_id, action_id, approved):
        return {"session_id": session_id, "reply": "stub decision", "state": "answered", "pending_action": None,
                "result": None, "citations": [], "tool_calls": []}


class RunnerAuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        auth = AuthService(root / "auth.sqlite3")
        auth.provision_employee("E-1", EMAIL, "Sara Mikhail", "Support")
        auth.set_password("E-1", "eval", PASSWORD)
        self.runtime = StubRuntime()
        self.client = TestClient(create_app(self.runtime, auth=auth))
        self.client.__enter__()                                   # runs the lifespan (installs the runtime)
        self.addCleanup(self.client.__exit__, None, None, None)
        self.creds_path = root / "eval-credentials.json"
        self.creds_path.write_text(json.dumps({"accounts": {EMAIL: PASSWORD}}), encoding="utf-8")
        self.urls = {"APP": "http://testserver"}

    def run_case(self, case, creds):
        return run_evals.run_case(case, self.urls, self.client, ROOT / "evals" / "cases.sample.jsonl", None, False, creds)

    def test_case_with_a_user_signs_in_and_keeps_its_inputs_and_expectations(self):
        case = {"id": "AUTH-1", "category": "happy_path", "turns": [{"say": "hello"}, {"say": "again"}],
                "user": {"email": EMAIL}, "expect": {"reply_contains_any": ["stub answer for sara.mikhail"], "pending_action": "none"}}
        result = self.run_case(case, run_evals.EvalCredentials(self.creds_path))
        self.assertTrue(result["passed"], result)
        self.assertEqual([u["email"] for u in self.runtime.users], [EMAIL, EMAIL])        # inputs untouched
        self.assertNotIn(PASSWORD, json.dumps(result))

    def test_one_login_is_reused_and_unknown_accounts_fail_clearly(self):
        creds = run_evals.EvalCredentials(self.creds_path)
        first = creds.token_for(self.client, "http://testserver", EMAIL.upper())
        self.assertEqual(creds.token_for(self.client, "http://testserver", EMAIL), first)
        with self.assertRaises(LookupError):
            creds.token_for(self.client, "http://testserver", "nobody@nakhla.example")
        case = {"id": "AUTH-2", "category": "happy_path", "turns": [{"say": "hi"}], "user": {"email": "nobody@nakhla.example"},
                "expect": {}}
        result = self.run_case(case, creds)
        self.assertFalse(result["passed"])
        self.assertIn("no eval credential", result["error"])

    def test_wrong_credentials_are_reported_without_the_password(self):
        bad = Path(self.tmp.name) / "bad.json"
        bad.write_text(json.dumps({"accounts": {EMAIL: "wrong-password-1"}}), encoding="utf-8")
        case = {"id": "AUTH-3", "category": "happy_path", "turns": [{"say": "hi"}], "user": {"email": EMAIL}, "expect": {}}
        result = self.run_case(case, run_evals.EvalCredentials(bad))
        self.assertIn("eval login failed", result["error"])
        self.assertNotIn("wrong-password-1", json.dumps(result))

    def test_a_case_without_a_user_is_sent_unauthenticated_and_refused(self):
        case = {"id": "S2-02-like", "category": "clarification", "turns": [{"say": "My VPN is not working. Can you fix it?"}],
                "expect": {"reply_contains_any": ["email"], "pending_action": "none"}}
        result = self.run_case(case, run_evals.EvalCredentials(self.creds_path))
        self.assertEqual(result["turns"][0]["status"], 401)
        self.assertEqual(self.runtime.users, [])                                          # the agent was never reached

    def test_missing_credentials_file_means_no_logins(self):
        creds = run_evals.EvalCredentials(Path(self.tmp.name) / "absent.json")
        with self.assertRaises(LookupError):
            creds.token_for(self.client, "http://testserver", EMAIL)


if __name__ == "__main__":
    unittest.main()
