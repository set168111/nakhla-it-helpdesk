"""Gradio UI - a small client of the app API contract, with local employee sign-in.

It never talks to the helpdesk API or the LLM directly. It only calls your app:
    POST {APP_URL}/api/login     {"email", "password"}          -> {"token", "employee"}
    POST {APP_URL}/api/chat      {"session_id", "message"}      Authorization: Bearer <token>
    POST {APP_URL}/api/approve   {"session_id", "action_id", "approved"}   Authorization: Bearer <token>
    POST {APP_URL}/api/logout
The identity is the signed-in employee; there is no email box and nothing typed can change it.
LOCAL DEMO ONLY. Run your app first (port 8000), then:   python ui/app_ui.py   ->  http://localhost:7860
"""
from __future__ import annotations

import html
import math
import os
import secrets

import gradio as gr
import httpx

APP_URL = os.getenv("APP_URL", "http://localhost:8000").rstrip("/")
PUBLIC_URL = os.getenv("APP_PUBLIC_URL", "http://localhost:8000").rstrip("/")   # what the BROWSER opens
NO_CARD = "_No ticket draft waiting for approval._"
NOT_SIGNED_IN = "_Not signed in._"
SIGN_IN_FIRST = "Please sign in first."
PUBLIC_MENU = [("Demo video", "/demo/video"), ("Presentation", "/demo/presentation"),
               ("App health", "/health"), ("Updates", "/demo/updates")]
ADMIN_MENU = [("Admin tickets", "/demo/tickets"), ("Demo accounts", "/demo/login")]
MENU = PUBLIC_MENU + ADMIN_MENU
ADMIN_LABEL = "For administrators — separate login required"


def new_session_id() -> str:
    return "ui-" + secrets.token_hex(12)


def menu_html() -> str:
    def links(items):
        return ''.join(f'<a href="{html.escape(PUBLIC_URL + path, quote=True)}" target="_blank" '
                       f'rel="noopener noreferrer">{html.escape(label)}</a>' for label, path in items)
    flex = 'display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;min-width:0;max-width:100%;box-sizing:border-box'
    return (f'<nav aria-label="Helpdesk links" style="{flex};padding:4px 0;gap:12px 24px">'
            f'<div role="group" aria-label="Helpdesk resources" style="{flex}">{links(PUBLIC_MENU)}</div>'
            f'<div role="group" aria-label="{html.escape(ADMIN_LABEL)}" '
            f'style="{flex};border:1px solid #aeb5bf;border-radius:4px;padding:8px 12px">'
            f'<span style="flex-basis:100%;font-size:.9em;overflow-wrap:anywhere">{html.escape(ADMIN_LABEL)}</span>'
            f'{links(ADMIN_MENU)}</div></nav>')


def call_app(path: str, body: dict | None = None, token: str | None = None) -> tuple[int, dict]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        r = httpx.post(f"{APP_URL}{path}", json=body or {}, headers=headers, timeout=180)
    except httpx.HTTPError as exc:
        return 0, {"reply": f"Cannot reach your app at {APP_URL} ({exc.__class__.__name__}). Is it running?"}
    try:
        data = r.json()
    except ValueError:
        data = {"reply": r.text[:500]}
    return r.status_code, data if isinstance(data, dict) else {"reply": str(data)}


def usage_markdown(usage) -> str:
    """Render only reported last-turn usage; no inferred missing zeros or ticket attribution."""
    usage = usage if isinstance(usage, dict) else {}

    def number(key):
        value = usage.get(key)
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 else None

    def tokens(key):
        value = number(key)
        return str(int(value)) if value is not None and value == int(value) else "Unknown"

    cost, settled, estimated, reserved = (number(key) for key in (
        "cost_usd", "confirmed_cost_usd", "calculated_cost_usd", "unknown_reserved_usd"))
    unknown = (reserved is not None and reserved > 0) or ("cost_usd" in usage and cost is None)
    lines = ["### Last-turn usage", f"- Input tokens: {tokens('prompt_tokens')}",
             f"- Output tokens: {tokens('completion_tokens')}"]
    if unknown:
        lines.append("- Cost (USD): Unknown (final billing incomplete)")
    elif cost is not None:
        basis = "" if settled is not None and estimated is not None and estimated <= settled else " (confirmation basis unavailable)"
        lines.append(f"- Cost (USD): {cost:.8f}" + basis)
    else:
        lines.append("- Cost (USD): Unknown")
    # In the existing API, confirmed_cost_usd is ALL settled spend, including estimates.
    if settled is not None and estimated is not None and estimated <= settled:
        lines += [f"- Confirmed cost (USD): {settled - estimated:.8f}",
                  f"- Estimated cost (USD): {estimated:.8f}"]
    else:
        if settled is not None:
            lines.append(f"- Settled cost (USD): {settled:.8f} (confirmation basis unavailable)")
        if estimated is not None:
            lines.append(f"- Estimated cost (USD): {estimated:.8f}")
    if reserved is not None and reserved > 0:
        lines.append(f"- Unknown usage reservation (USD): {reserved:.8f} (not a confirmed charge)")
    if unknown:
        lines.append("_Reported token counts may be partial; unreported usage is unknown._")
    return "\n".join(lines)


def side_panels(data: dict) -> tuple[str, str, str]:
    cites = data.get("citations") or []
    cite_md = "### Sources\n" + ("\n".join(
        f"- **{c.get('id', '?')}** {c.get('title', '')}" if isinstance(c, dict) else f"- {c}" for c in cites)
        or "_No knowledge-base article cited in the last answer._")
    calls = data.get("tool_calls") or []
    tools_md = "### Tool calls (last turn)\n" + ("\n".join(
        f"- `{t.get('tool', '?')}` {'ok' if t.get('ok') else 'FAILED'} · {t.get('ms', '?')} ms"
        for t in calls if isinstance(t, dict)) or "_none_")
    tools_md += "\n\n" + usage_markdown(data.get("usage"))
    result = data.get("result") or {}
    state = data.get("state")
    result_md = ""
    if result:
        result_md = "### Result\n" + "\n".join(f"- **{k}**: `{v}`" for k, v in result.items())
    if state:
        result_md += f"\n\n_Workflow state: {state}_"
    return cite_md, tools_md, result_md


def ticket_card(pending: dict | None) -> str:
    if not pending:
        return NO_CARD
    payload = pending.get("payload") or {}
    lines = [f"### Ticket draft - waiting for your approval", f"**{pending.get('summary', '')}**", ""]
    for key in ("subject", "category", "priority", "department", "requester_email", "affected_users"):
        if key in payload:
            lines.append(f"- **{key}**: {payload[key]}")
    if payload.get("attempted_steps"):
        lines.append("- **attempted steps**: " + "; ".join(map(str, payload["attempted_steps"])))
    if "kb_refs" in payload:
        lines.append("- **KB refs**: " + (", ".join(payload["kb_refs"]) or "none"))
    if payload.get("description"):
        lines += ["", f"> {payload['description']}"]
    return "\n".join(lines)


def show(data: dict, history: list):
    history = history + [{"role": "assistant", "content": data.get("reply") or "(empty reply)"}]
    pending = data.get("pending_action") or None
    cite_md, tools_md, result_md = side_panels(data)
    buttons = gr.update(interactive=bool(pending))
    return history, pending, ticket_card(pending), buttons, buttons, cite_md, tools_md, result_md


def who_text(employee: dict) -> str:
    return (f"Signed in as **{employee.get('name', '')}** · {employee.get('email', '')} · "
            f"{employee.get('department', '')} (read-only)")


def reset_panels() -> tuple:
    off = gr.update(interactive=False)
    return [], None, NO_CARD, off, off, "### Sources\n_No answer yet._", "### Tool calls\n_none_\n\n" + usage_markdown(None), ""


def session_ended(data: dict, status: int) -> bool:
    return status == 401 or data.get("state") == "authentication_required"


def send(message: str, history: list, session_id: str, token: str | None):
    if not message.strip():
        return ("", history, *[gr.skip()] * 9)
    history = history + [{"role": "user", "content": message}]
    if not token:
        return ("", *show({"reply": SIGN_IN_FIRST}, history), gr.skip(), gr.skip())
    status, data = call_app("/api/chat", {"session_id": session_id, "message": message}, token)
    if session_ended(data, status):
        data = {"reply": "Your sign-in has ended. Please sign in again."}
        return ("", *show(data, history), None, NOT_SIGNED_IN)
    return ("", *show(data, history), gr.skip(), gr.skip())


def decide(approved: bool, history: list, session_id: str, pending: dict | None, token: str | None):
    if not pending or not token:
        return (*show({"reply": "There is no draft to approve or reject." if token else SIGN_IN_FIRST}, history), gr.skip(), gr.skip())
    history = history + [{"role": "user", "content": "Approve" if approved else "Reject"}]
    status, data = call_app("/api/approve", {"session_id": session_id, "action_id": pending.get("action_id"),
                                             "approved": approved}, token)
    if session_ended(data, status):
        return (*show({"reply": "Your sign-in has ended. Please sign in again."}, history), None, NOT_SIGNED_IN)
    return (*show(data, history), gr.skip(), gr.skip())


def login(email: str, password: str, token: str | None):
    if token:                      # replacing a login ends the previous one
        call_app("/api/logout", None, token)
    status, data = call_app("/api/login", {"email": (email or "").strip(), "password": password or ""})
    if status == 200 and data.get("token"):
        return (data["token"], who_text(data.get("employee") or {}), "Signed in.", "", new_session_id(), *reset_panels())
    message = data.get("reply") or "Sign-in failed."
    return (None, NOT_SIGNED_IN, message, "", new_session_id(), *reset_panels())


def logout(token: str | None):
    if token:
        call_app("/api/logout", None, token)
    return (None, NOT_SIGNED_IN, "Signed out.", "", new_session_id(), *reset_panels())


with gr.Blocks(title="Nakhla IT Helpdesk") as demo:
    session = gr.State(new_session_id)
    token_state = gr.State(None)
    pending_state = gr.State(None)
    gr.Markdown("## Nakhla IT Helpdesk\nIT support assistant for Nakhla Systems (a fictional company). "
                "The helpdesk system behind it is simulated. Review every ticket draft before approving it. "
                "**LOCAL DEMO ONLY.**")
    gr.HTML(menu_html())
    with gr.Row():
        with gr.Column(scale=3):
            with gr.Group():
                email = gr.Textbox(label="Work email", placeholder="first.last@nakhla.example")
                password = gr.Textbox(label="Password", type="password")
                with gr.Row():
                    sign_in = gr.Button("Sign in", variant="primary")
                    sign_out = gr.Button("Sign out")
                login_msg = gr.Markdown("")
            who = gr.Markdown(NOT_SIGNED_IN)
            chat = gr.Chatbot(label="Chat", height=420)
            msg = gr.Textbox(label="Message", placeholder="Describe your IT problem, e.g. NakhlaConnect shows NX-781",
                             submit_btn=True)
            new_chat = gr.Button("New chat")
        with gr.Column(scale=2):
            with gr.Group():
                card = gr.Markdown(NO_CARD, padding=True)
                with gr.Row():
                    approve_btn = gr.Button("Approve", variant="primary", interactive=False)
                    reject_btn = gr.Button("Reject", variant="stop", interactive=False)
            result = gr.Markdown("")
            cites = gr.Markdown("### Sources\n_No answer yet._")
            tools = gr.Markdown("### Tool calls (last turn)\n_none_\n\n" + usage_markdown(None))
    outputs = [chat, pending_state, card, approve_btn, reject_btn, cites, tools, result]
    identity = [token_state, who]
    msg.submit(send, [msg, chat, session, token_state], [msg, *outputs, *identity])
    approve_btn.click(lambda h, s, p, t: decide(True, h, s, p, t), [chat, session, pending_state, token_state], [*outputs, *identity])
    reject_btn.click(lambda h, s, p, t: decide(False, h, s, p, t), [chat, session, pending_state, token_state], [*outputs, *identity])
    sign_in.click(login, [email, password, token_state], [token_state, who, login_msg, password, session, *outputs])
    password.submit(login, [email, password, token_state], [token_state, who, login_msg, password, session, *outputs])
    sign_out.click(logout, [token_state], [token_state, who, login_msg, password, session, *outputs])
    new_chat.click(lambda: (new_session_id(), *reset_panels()), outputs=[session, *outputs])

if __name__ == "__main__":
    demo.launch(server_name=os.getenv("UI_HOST", "127.0.0.1"), server_port=int(os.getenv("UI_PORT", "7860")))
