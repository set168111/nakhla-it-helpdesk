"""Test-only helpers for the mandatory local login.

Production code has no bypass. These wrappers log in through the real AuthService (in-memory,
provisioned on demand with a throwaway password) and attach the bearer token the way a real
client would, so existing HTTP-level tests exercise the production create_app wiring.
"""
from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from app.auth import AuthService
from app.main import create_app

TEST_PASSWORD = "test-only-password-not-a-secret"
GUARDED = ("/api/chat", "/api/approve")


def employee_id_for(email: str) -> str:
    return "T-" + email.split("@")[0]


def ensure_employee(auth: AuthService, email: str, name: str | None = None, department: str = "Test") -> str:
    auth.provision_employee(employee_id_for(email), email, name or email.split("@")[0], department)
    auth.set_password(employee_id_for(email), "demo", TEST_PASSWORD)
    return employee_id_for(email)


def make_auth(*emails: str, **options) -> AuthService:
    auth = AuthService(":memory:", **options)
    for email in emails:
        ensure_employee(auth, email)
    return auth


def create_test_app(runtime=None, auth: AuthService | None = None):
    return create_app(runtime, auth=auth or make_auth())


def claim_for(app, session_id: str, email: str) -> None:
    """Pre-claim a conversation that a test created directly in the store (no chat turn)."""
    assert app.state.auth.claim_session(session_id, ensure_employee(app.state.auth, email))


class _Identity:
    """Chooses which signed-in employee a request belongs to, like a real client would."""

    def __init__(self, auth: AuthService, default_email: str):
        self.auth, self.default_email = auth, default_email
        self.tokens: dict[str, str] = {}
        self.session_email: dict[str, str] = {}

    def token_for(self, email: str) -> str:
        if email not in self.tokens:
            ensure_employee(self.auth, email)
            self.tokens[email] = self.auth.login(email, TEST_PASSWORD)[0]
        return self.tokens[email]

    def headers_for(self, url: str, kwargs: dict) -> dict:
        if not url.endswith(GUARDED) or "authorization" in {k.lower() for k in (kwargs.get("headers") or {})}:
            return kwargs
        body = kwargs.get("json") or {}
        email = ((body.get("user") or {}).get("email") or self.session_email.get(body.get("session_id"))
                 or self.default_email)
        self.token_for(email)
        if url.endswith("/api/chat"):
            self.session_email.setdefault(body.get("session_id"), email)
        return {**kwargs, "headers": {**(kwargs.get("headers") or {}), "Authorization": "Bearer " + self.tokens[email]}}


class AuthedTestClient(TestClient):
    def __init__(self, app, default_email: str = "sara.mikhail@nakhla.example", **kwargs):
        super().__init__(app, **kwargs)
        self.identity = _Identity(app.state.auth, default_email)

    def post(self, url, **kwargs):
        return super().post(url, **self.identity.headers_for(url, kwargs))


class AuthedAsyncClient(httpx.AsyncClient):
    def __init__(self, *args, default_email: str = "sara.mikhail@nakhla.example", **kwargs):
        super().__init__(*args, **kwargs)
        self.identity = _Identity(kwargs["transport"].app.state.auth, default_email)

    async def post(self, url, **kwargs):
        return await super().post(url, **self.identity.headers_for(str(url), kwargs))
