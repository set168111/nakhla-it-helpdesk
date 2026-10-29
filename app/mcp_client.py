"""The application's single stdio connection to the unchanged supplied MCP server."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
READ_TOOLS = frozenset({"lookup_employee", "get_service_status", "search_tickets", "get_ticket"})
ALL_TOOLS = READ_TOOLS | {"create_ticket", "add_ticket_note"}


def tool_json(result) -> dict:
    data = getattr(result, "structuredContent", None)
    if isinstance(data, dict):
        return data["result"] if set(data) == {"result"} and isinstance(data["result"], dict) else data
    for part in result.content or []:
        if getattr(part, "type", "") == "text":
            try:
                return json.loads(part.text)
            except ValueError:
                break
    return {"ok": False, "error": {"code": "invalid_tool_response", "message": "The system returned no valid structured result."}}


class MCPClient:
    def __init__(self, timeout: float = 10):
        self.timeout = timeout
        self.session = None
        self.trace: list[dict] = []
        self.stack = None
        self._lock = asyncio.Lock()

    async def __aenter__(self):
        self.stack = AsyncExitStack()
        try:
            env = dict(os.environ)
            env["HELPDESK_TIMEOUT_S"] = "8"
            params = StdioServerParameters(command=sys.executable, args=["-m", "services.helpdesk_mcp"], cwd=str(ROOT), env=env)
            read, write = await self.stack.enter_async_context(stdio_client(params))
            self.session = await self.stack.enter_async_context(ClientSession(read, write))
            await asyncio.wait_for(self.session.initialize(), self.timeout)
            names = {tool.name for tool in (await self.session.list_tools()).tools}
            if names != ALL_TOOLS:
                raise RuntimeError("Supplied MCP tool inventory differs from expected six tools")
            return self
        except BaseException:
            await self.stack.aclose()
            self.session = None
            raise

    async def __aexit__(self, *args):
        if self.stack:
            await self.stack.aclose()
        self.session = None

    def drain_trace(self) -> list[dict]:
        trace, self.trace = self.trace, []
        return trace

    async def _invoke(self, name: str, arguments: dict) -> dict:
        start = time.monotonic()
        try:
            if self.session is None:
                raise ConnectionError("MCP connection is not ready")
            async with asyncio.timeout(self.timeout):
                async with self._lock:
                    result = await self.session.call_tool(name, arguments)
            data = tool_json(result)
        except (TimeoutError, ConnectionError, OSError):
            data = {"ok": False, "error": {"code": "timeout", "message": "The operation outcome is not confirmed."}}
        except Exception:
            data = {"ok": False, "error": {"code": "mcp_error", "message": "The helpdesk connection failed; no outcome is confirmed."}}
        self.trace.append({"tool": name, "ok": bool(data.get("ok")), "ms": round((time.monotonic() - start) * 1000)})
        return data

    async def call(self, name: str, arguments: dict | None = None) -> dict:
        if name not in READ_TOOLS:
            raise PermissionError("Only allowlisted read tools can be selected by the agent")
        return await self._invoke(name, arguments or {})

    async def create_approved_ticket(self, payload: dict, action_id: str) -> dict:
        """Approval coordinator only: payload from the claimed immutable ledger row."""
        if not action_id.startswith("act-"):
            raise ValueError("An approval action identity is required")
        return await self._invoke("create_ticket", {**payload, "idempotency_key": action_id})
