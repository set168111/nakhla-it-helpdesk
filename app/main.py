"""Exact shared HTTP contract. One worker owns one stdio MCP child."""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)


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


def create_app(runtime=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(api):
        if runtime is not None:
            api.state.runtime = runtime
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
        store.purge_history()
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
    lock = asyncio.Lock()

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

    @api.post("/api/chat")
    async def chat(body: ChatRequest):
        async with lock:
            result = await api.state.runtime.chat(body.session_id, body.message, body.user.model_dump() if body.user else None)
            # Paid paths always supply metered usage; only early deterministic
            # responses reach here without it. Never overwrite unknown billing.
            result.setdefault("usage", {"cost_usd": 0, "confirmed_cost_usd": 0, "unknown_reserved_usd": 0})
            return result

    @api.post("/api/approve")
    async def approve(body: ApproveRequest):
        async with lock:
            result = await api.state.runtime.approvals.decide(body.session_id, body.action_id, body.approved)
            result.setdefault("usage", {"cost_usd": 0, "confirmed_cost_usd": 0, "unknown_reserved_usd": 0})
            return result

    return api


app = create_app()
