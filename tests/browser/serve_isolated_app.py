"""ISOLATED stack for the browser smoke test: a stub chat runtime behind the REAL create_app wiring,
a temporary AuthService with throwaway test accounts, a temporary credential sheet and a dummy simulator.
No model, no embeddings, no live data, no real secrets. Ports come from the environment.

Run with the project interpreter (started by tests/browser/ui_smoke.py):
    .venv/Scripts/python.exe -B tests/browser/serve_isolated_app.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

APP_PORT, SIM_PORT = int(os.environ["ISO_APP_PORT"]), int(os.environ["ISO_SIM_PORT"])
ACCOUNTS = [("E-9001", "tester.one@nakhla.example", "Tester One", "Support", "throwaway-test-password-1"),
            ("E-9002", "tester.two@nakhla.example", "Tester Two", "Sales", "throwaway-test-password-2")]
ADMIN_PASSWORD = "throwaway-admin-password"
from tests.ui_fixtures import USAGE, TICKETS as FIXTURE_TICKETS
TICKETS = {"count": len(FIXTURE_TICKETS), "tickets": FIXTURE_TICKETS}


class Simulator(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps(TICKETS).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class StubRuntime:
    retrieval = type("Retrieval", (), {"ready": True})()
    client = object()

    def __init__(self):
        self.approvals = self
        self.seen_users: list = []

    async def chat(self, session_id, message, user):
        self.seen_users.append(user)
        result = {"session_id": session_id, "reply": f"[stub] {user['email']} wrote: {message}", "state": "answered",
                  "pending_action": None, "result": None, "citations": [], "tool_calls": []}
        usage = USAGE.get(message.removeprefix('fixture-'), USAGE['confirmed'])
        result['usage'] = usage  # explicit null fixture exercises unavailable values through the real UI
        return result

    async def decide(self, session_id, action_id, approved):
        return {"session_id": session_id, "reply": "stub decision", "state": "answered", "pending_action": None,
                "result": None, "citations": [], "tool_calls": []}


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="iso-ui-"))
    sheet = tmp / "demo-accounts.json"
    sheet.write_text(json.dumps({"note": "LOCAL DEMO ONLY", "accounts": [
        {"email": e, "name": n, "department": d, "password": p} for _, e, n, d, p in ACCOUNTS]}), encoding="utf-8")
    video, deck = tmp / "video.mp4", tmp / "deck.html"
    video.write_bytes(b"\x00\x00\x00\x18ftypmp42isolated")
    deck.write_text("<html><body>isolated deck</body></html>", encoding="utf-8")
    os.environ.update({"DEMO_SHEET_PATH": str(sheet), "DEMO_VIDEO_PATH": str(video), "DEMO_PRESENTATION_PATH": str(deck),
                       "SIMULATOR_ADMIN_URL": f"http://127.0.0.1:{SIM_PORT}"})
    threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", SIM_PORT), Simulator).serve_forever, daemon=True).start()
    from app.auth import AuthService
    from app.main import create_app
    auth = AuthService(tmp / "auth.sqlite3")
    for employee_id, email, name, department, password in ACCOUNTS:
        auth.provision_employee(employee_id, email, name, department)
        auth.set_password(employee_id, "demo", password)
    auth.set_admin_password(ADMIN_PASSWORD)
    import uvicorn
    uvicorn.run(create_app(StubRuntime(), auth=auth), host="127.0.0.1", port=APP_PORT, log_level="warning")


if __name__ == "__main__":
    main()
