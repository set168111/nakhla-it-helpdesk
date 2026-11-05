"""OFFLINE tests for the LOCAL DEMO ONLY instructor pages (app/demo_admin.py).

Real create_app wiring, a real AuthService on a temporary database, a stdlib dummy simulator on a free
loopback port, temporary credential sheet and asset files. Nothing touches the real secrets/ or data/.

Run: python -B -m unittest tests.test_demo_admin -v
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.auth import AuthService
from app.main import create_app
from tests.test_agent_workflow import FakeMCP
from tests.test_auth_service import Clock

ADMIN_PASSWORD = "admin-demo-password-xyz"
SHEET = {"note": "LOCAL DEMO ONLY", "accounts": [
    {"email": "sara.mikhail@nakhla.example", "name": "Sara Mikhail", "department": "Support", "password": "SHEET-PASS-sara-111"},
    {"email": "omar.farah@nakhla.example", "name": "Omar <b>Farah</b>", "department": "Sales", "password": "SHEET-PASS-omar-222"}]}
TICKETS = {"tickets": [{"ticket_id": "IT-2001", "requester_email": "omar.farah@nakhla.example",
                        "subject": "<script>alert(1)</script> Wireshark", "category": "software", "priority": "P4",
                        "status": "open", "created_at": "2026-11-04T10:00:00Z"}], "count": 1}


class DummySimulator(BaseHTTPRequestHandler):
    hits: list[str] = []

    def do_GET(self):
        DummySimulator.hits.append(self.path)
        body = json.dumps(TICKETS).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class DemoAdminBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), DummySimulator)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / "secrets").mkdir()
        self.sheet = root / "secrets" / "demo-accounts.json"
        self.sheet.write_text(json.dumps(SHEET), encoding="utf-8")
        self.video, self.deck = root / "v.mp4", root / "deck.html"
        self.video.write_bytes(b"\x00\x00\x00\x18ftypmp42-demo-video-bytes")
        self.deck.write_text("<html><body>demo deck</body></html>", encoding="utf-8")
        self.secret_outside = root / "outside-secret.txt"
        self.secret_outside.write_text("TOP-SECRET-OUTSIDE", encoding="utf-8")
        self.clock = Clock()
        self.auth = AuthService(root / "auth.sqlite3", clock=self.clock, max_failures=3)
        self.auth.set_admin_password(ADMIN_PASSWORD)
        self.auth.provision_employee("E-1", "sara.mikhail@nakhla.example", "Sara Mikhail", "Support")
        self.auth.set_password("E-1", "demo", "sara-real-employee-password")
        env = {"DEMO_SHEET_PATH": str(self.sheet), "DEMO_VIDEO_PATH": str(self.video), "DEMO_PRESENTATION_PATH": str(self.deck),
               "SIMULATOR_ADMIN_URL": f"http://127.0.0.1:{self.server.server_address[1]}"}
        patcher = patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        runtime = FakeMCPRuntime()
        self.client = TestClient(create_app(runtime, auth=self.auth), follow_redirects=False)

    def admin_login(self, password=ADMIN_PASSWORD):
        return self.client.post("/demo/login", data={"password": password})


class FakeMCPRuntime:
    retrieval = type("R", (), {"ready": True})()
    client = object()
    approvals = None

    async def chat(self, *args):
        raise AssertionError("the demo pages never call the chat runtime")


class AccessControlTests(DemoAdminBase):
    def test_every_admin_page_redirects_to_the_login_without_a_session(self):
        for path in ("/demo/accounts", "/demo/tickets"):
            response = self.client.get(path)
            self.assertEqual((response.status_code, response.headers["location"]), (303, "/demo/login"), path)
            self.assertNotIn("SHEET-PASS", response.text)
        self.assertEqual(DummySimulator.hits, [])                        # the simulator is not even contacted

    def test_wrong_password_is_generic_throttled_and_sets_no_cookie(self):
        for _ in range(3):
            response = self.admin_login("wrong")
            self.assertEqual(response.status_code, 401)
            self.assertNotIn("set-cookie", response.headers)
            self.assertIn("Invalid demo admin password.", response.text)
        locked = self.admin_login(ADMIN_PASSWORD)
        self.assertEqual(locked.status_code, 429)
        self.assertIn("Retry-After", locked.headers)
        self.assertNotIn("set-cookie", locked.headers)

    def test_login_sets_a_strict_httponly_cookie_scoped_to_the_demo_path(self):
        response = self.admin_login()
        self.assertEqual((response.status_code, response.headers["location"]), (303, "/demo/accounts"))
        cookie = response.headers["set-cookie"].lower()
        for part in ("httponly", "samesite=strict", "path=/demo"):
            self.assertIn(part, cookie)

    def test_employee_login_and_employee_token_do_not_open_admin_pages(self):
        employee_token = self.auth.login("sara.mikhail@nakhla.example", "sara-real-employee-password")[0]
        self.client.cookies.set("demo_admin", employee_token)
        self.assertEqual(self.client.get("/demo/accounts").status_code, 303)
        self.assertEqual(self.admin_login("sara-real-employee-password").status_code, 401)

    def test_admin_cookie_never_impersonates_an_employee(self):
        self.admin_login()
        response = self.client.post("/api/chat", json={"session_id": "adm-1", "message": "Show my tickets."})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.client.get("/api/me").status_code, 401)

    def test_logout_and_expiry_end_the_admin_session(self):
        self.admin_login()
        self.assertEqual(self.client.get("/demo/accounts").status_code, 200)
        self.assertEqual(self.client.post("/demo/logout").status_code, 303)
        self.assertEqual(self.client.get("/demo/accounts").status_code, 303)
        self.admin_login()
        self.clock.now += 3601
        self.assertEqual(self.client.get("/demo/accounts").status_code, 303)


class PageContentTests(DemoAdminBase):
    def setUp(self):
        super().setUp()
        self.admin_login()

    def test_accounts_page_is_labelled_has_copy_buttons_and_is_never_cached(self):
        response = self.client.get("/demo/accounts")
        self.assertEqual(response.status_code, 200)
        self.assertIn("LOCAL DEMO ONLY", response.text)
        for email in ("sara.mikhail@nakhla.example", "omar.farah@nakhla.example"):
            self.assertIn(f'data-copy="{email}"', response.text)                       # copy email
        for password in ("SHEET-PASS-sara-111", "SHEET-PASS-omar-222"):
            self.assertIn(f'data-copy="{password}"', response.text)                    # copy password
        visible = response.text.split("<table>")[1]
        self.assertEqual(visible.count("Copy password"), 2)
        self.assertEqual(response.headers["cache-control"], "no-store")
        csp = response.headers["content-security-policy"]
        self.assertIn("default-src 'none'", csp)
        self.assertIn("script-src 'nonce-", csp)
        self.assertNotIn("script-src 'unsafe-inline'", csp)

    def test_values_are_html_escaped(self):
        response = self.client.get("/demo/accounts")
        self.assertNotIn("<b>Farah</b>", response.text)
        self.assertIn("&lt;b&gt;Farah&lt;/b&gt;", response.text)
        tickets = self.client.get("/demo/tickets")
        self.assertEqual(tickets.status_code, 200)
        self.assertNotIn("<script>alert(1)</script>", tickets.text)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", tickets.text)

    def test_tickets_page_is_read_only_and_only_lists_tickets(self):
        DummySimulator.hits.clear()
        response = self.client.get("/demo/tickets")
        self.assertIn("IT-2001", response.text)
        self.assertEqual(DummySimulator.hits, ["/admin/tickets?all=true", "/admin/tickets"])  # read-only authoritative sources
        for path in ("/demo/reset", "/demo/faults", "/demo/admin/reset"):
            self.assertEqual(self.client.post(path).status_code, 404, path)

    def test_unreachable_simulator_is_reported_not_leaked(self):
        with patch.dict(os.environ, {"SIMULATOR_ADMIN_URL": "http://127.0.0.1:9"}):
            response = self.client.get("/demo/tickets")
        self.assertEqual(response.status_code, 502)
        self.assertIn("could not be reached", response.text)

    def test_missing_sheet_shows_setup_hint_without_error(self):
        self.sheet.unlink()
        response = self.client.get("/demo/accounts")
        self.assertEqual(response.status_code, 200)
        self.assertIn("setup_demo_auth.py", response.text)


class SecretExposureTests(DemoAdminBase):
    def test_exactly_two_assets_are_served_and_nothing_resolves_from_the_path(self):
        video = self.client.get("/demo/video")
        deck = self.client.get("/demo/presentation")
        self.assertEqual((video.status_code, video.headers["content-type"]), (200, "video/mp4"))
        self.assertEqual(video.content, self.video.read_bytes())
        self.assertEqual(deck.status_code, 200)
        self.assertEqual(deck.headers["content-security-policy"], "sandbox allow-scripts")
        for path in ("/demo/../secrets/demo-accounts.json", "/demo/%2e%2e/secrets/demo-accounts.json", "/demo/accounts.json",
                     "/demo/demo-accounts.json", "/secrets/demo/demo-accounts.json", "/secrets/demo-accounts.json",
                     "/static/demo-accounts.json", "/demo/video/../../outside-secret.txt", "/demo/assets/" + self.secret_outside.name,
                     "/demo/files/" + self.sheet.name, "/data/auth.sqlite3", "/docs/security-fix-plan.md"):
            response = self.client.get(path)
            self.assertIn(response.status_code, {303, 404, 405}, path)
            self.assertNotIn("SHEET-PASS", response.text)
            self.assertNotIn("TOP-SECRET-OUTSIDE", response.text)

    def test_ordinary_user_responses_never_contain_the_demo_sheet_passwords(self):
        login = self.client.post("/api/login", json={"email": "sara.mikhail@nakhla.example", "password": "sara-real-employee-password"})
        wrong = self.client.post("/api/login", json={"email": "sara.mikhail@nakhla.example", "password": "SHEET-PASS-sara-111"})
        me = self.client.get("/api/me", headers={"Authorization": "Bearer " + login.json()["token"]})
        pages = [login, wrong, me, self.client.get("/demo/login"), self.client.get("/openapi.json")]
        for response in pages:
            self.assertNotIn("SHEET-PASS", response.text)
            self.assertNotIn(ADMIN_PASSWORD, response.text)
        self.assertEqual(wrong.status_code, 401)           # the sheet password is not the employee password here


if __name__ == "__main__":
    unittest.main()
