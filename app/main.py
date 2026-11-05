"""Exact shared HTTP contract. One worker owns one stdio MCP child.

BEHAVIOURAL CONTRACT CHANGE (local demo login): /api/chat and /api/approve now require a
signed-in employee (Authorization: Bearer from POST /api/login). Paths and JSON field names
are unchanged, but an unauthenticated call is refused. There is no bypass mode.
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from .auth import AuthService, LoginThrottled, Principal, legacy_session_ids

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)

SIGN_IN_REPLY = "Please sign in with your work email and password to use the helpdesk assistant."
UNAVAILABLE_REPLY = "This conversation is not available for your account. Start a new chat."
IDENTITY_CONFLICT_REPLY = "The supplied identity does not match your signed-in account."
ZERO_USAGE = {"cost_usd": 0, "confirmed_cost_usd": 0, "unknown_reserved_usd": 0}


class User(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(pattern=r"^[a-zA-Z0-9._-]+@nakhla\.example$", max_length=100)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(min_length=1, max_length=100, pattern=r"^[\w.-]+$")
    message: str = Field(min_length=1, max_length=4000)
    user: User | None = None


class ApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(min_length=1, max_length=100, pattern=r"^[\w.-]+$")
    action_id: str = Field(min_length=1, max_length=100)
    approved: StrictBool


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(max_length=120)
    password: str = Field(min_length=1, max_length=256)


def bearer_token(request: Request) -> str | None:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    return token.strip() or None if scheme.lower() == "bearer" else None


def refusal(status: int, session_id: str, reply: str, state: str, **headers: str) -> JSONResponse:
    """A ChatResponse-shaped refusal: nothing was read, changed or written."""
    return JSONResponse(status_code=status, headers=headers or None, content={
        "session_id": session_id, "reply": reply, "state": state, "pending_action": None, "result": None,
        "citations": [], "tool_calls": [], "usage": dict(ZERO_USAGE)})


def create_app(runtime=None, auth: AuthService | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(api):
        if runtime is not None:
            api.state.runtime = runtime
            api.state.auth = auth or AuthService(":memory:")   # no accounts: every login fails closed
            yield
            return
        from .agent import SupportWorkflow
        from .approvals import Approvals
        from .mcp_client import MCPClient
        from .retrieval import Retrieval
        from .storage import Store
        data = Path(os.getenv("APP_DATA_DIR", ROOT / "data"))
        data.mkdir(parents=True, exist_ok=True)
        store = Store(data / "helpdesk.sqlite3")
        store.recover_interrupted()
        # Authentication: conversations stored before login existed are retired (never adopted, never
        # deleted). Expiry is checked on access; destructive retention is explicit maintenance only.
        api.state.auth = auth or AuthService(data / "auth.sqlite3")
        api.state.auth.retire_legacy_sessions(legacy_session_ids(data / "helpdesk.sqlite3"))
        retrieval = Retrieval(data_dir=data)
        async with MCPClient() as mcp:
            approvals = Approvals(store, mcp, current_fingerprint=lambda: Retrieval(data_dir=data).fingerprint)
            workflow = SupportWorkflow(store, mcp, retrieval, approvals, data_dir=data)
            api.state.runtime = workflow
            try:
                yield
            finally:
                if workflow.client:
                    await workflow.client.close()
    api = FastAPI(title="Nakhla Helpdesk", lifespan=lifespan)
    api.state.auth = auth or (AuthService(":memory:") if runtime is not None else None)
    lock = asyncio.Lock()

    @api.exception_handler(RequestValidationError)
    async def validation_failed(_request: Request, exc: RequestValidationError):
        # Never echo submitted values (a rejected login body would otherwise return the password).
        errors = [{key: value for key, value in error.items() if key not in {"input", "ctx", "url"}} for error in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})

    from .demo_admin import build_demo_router
    api.include_router(build_demo_router(lambda: api.state.auth, root=ROOT))

    @api.get("/health")
    async def health():
        current = api.state.runtime
        if not current.retrieval.ready or not current.client:
            return JSONResponse({"status": "not_ready", "reason": "real_embedding_index_or_provider_credential_missing"}, status_code=503)
        if hasattr(current, "mcp"):
            async with lock:
                status = await current.mcp.call("get_service_status", {})
                current.mcp.drain_trace()
            if not status.get("ok"):
                return JSONResponse({"status": "not_ready", "reason": "helpdesk_mcp_unavailable"}, status_code=503)
        return {"status": "ok"}

    @api.post("/api/login")
    async def login(body: LoginRequest):
        try:
            result = await asyncio.to_thread(api.state.auth.login, body.email, body.password)
        except LoginThrottled as exc:
            return JSONResponse(status_code=429, headers={"Retry-After": str(exc.retry_after)},
                                content={"error": "too_many_attempts", "reply": "Too many sign-in attempts. Try again later."})
        if result is None:
            return JSONResponse(status_code=401, content={"error": "invalid_credentials", "reply": "Invalid email or password."})
        token, expires_at, principal = result
        return {"token": token, "expires_at": expires_at, "employee": employee_view(principal)}

    @api.post("/api/logout")
    async def logout(request: Request):
        revoked = api.state.auth.logout(bearer_token(request))
        if not revoked:
            return JSONResponse(status_code=401, content={"error": "not_signed_in", "reply": SIGN_IN_REPLY})
        return {"status": "signed_out"}

    @api.get("/api/me")
    async def me(request: Request):
        principal = api.state.auth.authenticate(bearer_token(request))
        if principal is None:
            return JSONResponse(status_code=401, content={"error": "not_signed_in", "reply": SIGN_IN_REPLY},
                                headers={"WWW-Authenticate": "Bearer"})
        return {"employee": employee_view(principal)}

    @api.post("/api/chat")
    async def chat(body: ChatRequest, request: Request):
        # Order matters: identity, then ownership, and only then anything that can read or change state.
        principal = api.state.auth.authenticate(bearer_token(request))
        if principal is None:
            return refusal(401, body.session_id, SIGN_IN_REPLY, "authentication_required", **{"WWW-Authenticate": "Bearer"})
        if body.user and body.user.email.lower() != principal.email:
            return refusal(403, body.session_id, IDENTITY_CONFLICT_REPLY, "identity_conflict")
        if not api.state.auth.claim_session(body.session_id, principal.employee_id):
            return refusal(403, body.session_id, UNAVAILABLE_REPLY, "session_unavailable")
        async with lock:
            # A queued request may outlive logout/expiry while another turn runs.
            if api.state.auth.authenticate(bearer_token(request)) is None:
                return refusal(401, body.session_id, SIGN_IN_REPLY, "authentication_required",
                               **{"WWW-Authenticate": "Bearer"})
            result = await api.state.runtime.chat(body.session_id, body.message, {"email": principal.email})
            # Paid paths always supply metered usage; only early deterministic
            # responses reach here without it. Never overwrite unknown billing.
            result.setdefault("usage", dict(ZERO_USAGE))
            return result

    @api.post("/api/approve")
    async def approve(body: ApproveRequest, request: Request):
        principal = api.state.auth.authenticate(bearer_token(request))
        if principal is None:
            return refusal(401, body.session_id, SIGN_IN_REPLY + " No new write was sent.", "authentication_required",
                           **{"WWW-Authenticate": "Bearer"})
        if not api.state.auth.owns_session(body.session_id, principal.employee_id):
            return refusal(403, body.session_id, UNAVAILABLE_REPLY + " No new write was sent.", "session_unavailable")
        async with lock:
            if api.state.auth.authenticate(bearer_token(request)) is None:
                return refusal(401, body.session_id, SIGN_IN_REPLY + " No new write was sent.",
                               "authentication_required", **{"WWW-Authenticate": "Bearer"})
            result = await api.state.runtime.approvals.decide(body.session_id, body.action_id, body.approved)
            result.setdefault("usage", dict(ZERO_USAGE))
            return result

    return api


def employee_view(principal: Principal) -> dict:
    return {"email": principal.email, "name": principal.name, "department": principal.department}


app = create_app()
