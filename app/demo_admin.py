"""LOCAL DEMO ONLY: instructor pages behind a separate demo-admin login.

- /demo/accounts shows the demo credential sheet (copy buttons). The sheet is a server-side file
  stored apart from the password hashes and is never served as a static file.
- /demo/tickets shows the simulator ticket list read-only, so the simulator port is not needed
  by browsers. Reset and fault controls are not exposed anywhere.
- The admin session is a different kind of login session: it cannot call /api/chat or /api/approve
  and never impersonates an employee.
- /demo/video and /demo/presentation serve exactly two allow-listed files, nothing else.
"""
from __future__ import annotations

import html
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

from .auth import AuthService, LoginThrottled

COOKIE = "demo_admin"
STYLE = ("body{font-family:system-ui,sans-serif;margin:0;background:#f6f7f9;color:#1b1f24}"
         "header{background:#7a1f1f;color:#fff;padding:10px 20px;font-weight:700;letter-spacing:.04em}"
         "main{max-width:1000px;margin:20px auto;padding:0 16px}nav a,nav button{margin-right:12px}"
         "table{border-collapse:collapse;width:100%;background:#fff}th,td{border:1px solid #d8dce1;padding:6px 8px;text-align:left}"
         "th{background:#eceff3}button,input[type=submit]{cursor:pointer}.warn{color:#7a1f1f;font-weight:700}"
         "code{background:#eceff3;padding:1px 4px}")


def _first_existing(*candidates: str | Path | None) -> Path | None:
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


def ticket_sort_key(ticket: dict) -> tuple:
    status = str(ticket.get("status", "")).strip().lower()
    group = 0 if status == "open" else 1 if status in {"resolved", "closed"} else 2
    try:
        created = datetime.fromisoformat(str(ticket.get("created_at", "")).replace("Z", "+00:00"))
        timestamp = created.replace(tzinfo=created.tzinfo or timezone.utc).timestamp()
    except (ValueError, TypeError, OverflowError, OSError):
        timestamp = float("-inf")  # missing/invalid dates last within their status group
    return group, -timestamp, str(ticket.get("ticket_id", ""))


def ticket_index(data: dict) -> dict:
    """Validate a complete simulator listing; keep newest duplicate within this source."""
    if not isinstance(data, dict) or not isinstance(data.get("tickets"), list):
        raise ValueError("Invalid ticket listing")
    records = data["tickets"]
    if type(data.get("count")) is not int or data["count"] != len(records):
        raise ValueError("Incomplete ticket listing")
    if any(not isinstance(t, dict) or not isinstance(t.get("ticket_id"), str) or not t["ticket_id"].strip()
           for t in records):
        raise ValueError("Missing ticket identity")
    indexed = {}
    for ticket in sorted(records, key=lambda t: ticket_sort_key(t)[1]):
        indexed.setdefault(ticket["ticket_id"].strip().upper(), ticket)
    return indexed


def build_demo_router(get_auth: Callable[[], AuthService], *, root: Path) -> APIRouter:
    router = APIRouter(prefix="/demo")
    sheet_path = Path(os.getenv("DEMO_SHEET_PATH", root / "secrets" / "demo" / "demo-accounts.json"))

    def page(title: str, body: str, *, status: int = 200, script: str = "") -> HTMLResponse:
        nonce = secrets.token_urlsafe(12)
        script_tag = f'<script nonce="{nonce}">{script}</script>' if script else ""
        content = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{html.escape(title)}</title>'
                   f"<style>{STYLE}</style></head><body><header>LOCAL DEMO ONLY &mdash; not a production system</header>"
                   f"<main><h1>{html.escape(title)}</h1>{body}</main>{script_tag}</body></html>")
        csp = f"default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-{nonce}'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
        return HTMLResponse(content, status_code=status, headers={
            "Cache-Control": "no-store", "Content-Security-Policy": csp, "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer"})

    def is_admin(request: Request) -> bool:
        return get_auth().authenticate_admin(request.cookies.get(COOKIE))

    def to_login() -> RedirectResponse:
        return RedirectResponse("/demo/login", status_code=303)

    NAV = ('<nav><a href="/demo/video">Demo video</a><a href="/demo/presentation">Presentation</a>'
           '<a href="/demo/tickets">Admin tickets</a><a href="/health">App health</a>'
           '<a href="/demo/login">Demo accounts</a>'
           '<form method="post" action="/demo/logout" style="display:inline"><button type="submit">Sign out</button></form></nav>')

    def login_form(message: str = "", status: int = 200) -> HTMLResponse:
        notice = f'<p class="warn">{html.escape(message)}</p>' if message else ""
        return page("Demo admin sign-in", notice + '<p>This page is for the instructor only. It does not sign you in as an employee.</p>'
                    '<form method="post" action="/demo/login"><label>Demo admin password '
                    '<input type="password" name="password" autocomplete="off" required></label> '
                    '<input type="submit" value="Sign in"></form>', status=status)

    @router.get("/login")
    async def login_page(request: Request):
        return RedirectResponse("/demo/accounts", status_code=303) if is_admin(request) else login_form()

    @router.post("/login")
    async def login_submit(password: str = Form("")):
        try:
            result = get_auth().admin_login(password)
        except LoginThrottled as exc:
            response = login_form("Too many attempts. Try again later.", 429)
            response.headers["Retry-After"] = str(exc.retry_after)
            return response
        if result is None:
            return login_form("Invalid demo admin password.", 401)
        token, _expires = result
        response = RedirectResponse("/demo/accounts", status_code=303)
        response.set_cookie(COOKIE, token, httponly=True, samesite="strict", path="/demo", max_age=3600)
        return response

    @router.post("/logout")
    async def logout(request: Request):
        auth = get_auth()
        auth.logout(request.cookies.get(COOKIE))
        response = RedirectResponse("/demo/login", status_code=303)
        response.delete_cookie(COOKIE, path="/demo")
        return response

    @router.get("/accounts")
    async def accounts(request: Request):
        if not is_admin(request):
            return to_login()
        if not sheet_path.is_file():
            return page("Demo accounts", NAV + "<p>No credential sheet exists yet. Run scripts/setup_demo_auth.py.</p>")
        sheet = json.loads(sheet_path.read_text(encoding="utf-8"))
        rows = []
        for account in sheet.get("accounts", []):
            email, password = html.escape(account["email"], quote=True), html.escape(account["password"], quote=True)
            rows.append(f"<tr><td>{html.escape(account['name'])}</td><td>{html.escape(account['department'])}</td>"
                        f'<td>{email} <button type="button" data-copy="{email}">Copy email</button></td>'
                        f'<td><code>&bull;&bull;&bull;&bull;&bull;&bull;</code> <button type="button" data-copy="{password}">Copy password</button></td></tr>')
        body = (NAV + '<p class="warn">LOCAL DEMO ONLY. Passwords are simulated demo credentials. Signing in here does not impersonate anyone.</p>'
                "<table><tr><th>Employee</th><th>Department</th><th>Email</th><th>Password</th></tr>" + "".join(rows) + "</table>")
        script = ("document.querySelectorAll('button[data-copy]').forEach(function(b){b.addEventListener('click',function(){"
                  "var t=b.dataset.copy;var done=function(){var o=b.textContent;b.textContent='Copied';setTimeout(function(){b.textContent=o},1200)};"
                  "if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(t).then(done)}else{"
                  "var a=document.createElement('textarea');a.value=t;document.body.appendChild(a);a.select();document.execCommand('copy');a.remove();done()}})});")
        return page("Demo accounts", body, script=script)

    @router.get("/tickets")
    async def tickets(request: Request):
        if not is_admin(request):
            return to_login()
        base = (os.getenv("SIMULATOR_ADMIN_URL") or os.getenv("HELPDESK_API_URL") or "http://localhost:8102").rstrip("/")
        sources = {}
        async with httpx.AsyncClient(timeout=5) as client:
            # Supported simulator sources: all=true includes the supplied archive AND created
            # records; the unchanged default endpoint identifies the created subset.
            for source, suffix in (("All tickets", "?all=true"), ("Created tickets", "")):
                try:
                    response = await client.get(base + "/admin/tickets" + suffix)
                    response.raise_for_status()
                    sources[source] = ticket_index(response.json())
                except (httpx.HTTPError, ValueError):
                    sources[source] = None
        all_tickets, created = sources["All tickets"], sources["Created tickets"]
        combined = {key: (ticket, "Historical" if created is not None else "Unavailable")
                    for key, ticket in (all_tickets or {}).items()}
        # Created is authoritative for duplicate IDs, including a collision with the archive.
        combined.update({key: (ticket, "Created") for key, ticket in (created or {}).items()})
        complete = all_tickets is not None and created is not None
        total = str(len(combined)) if all_tickets is not None else "Unavailable"
        historical_count = str(sum(origin == "Historical" for _, origin in combined.values())) if complete else "Unavailable"
        created_count = str(len(created)) if created is not None else "Unavailable"
        summary = (f"<p>Total: {total} | Historical: {historical_count} | Created: {created_count}"
                   f" (unique ticket IDs; {len(combined)} loaded; read-only).</p>")
        if not complete:
            failed = ", ".join(name for name, records in sources.items() if records is None)
            summary = ('<p class="warn">Incomplete view: ' + html.escape(failed) +
                       ' source unavailable or invalid. The simulator could not be reached or returned an incomplete listing. '
                       'Unavailable counts are unknown, not zero. Refresh to retry.</p>' + summary)
        columns = ("ticket_id", "created_at", "subject", "category", "priority", "status", "requester_email")
        rows = "".join("<tr>" + "".join(f"<td>{html.escape(str(item.get(column, '')))}</td>" for column in columns)
                       + f"<td>{html.escape(origin)}</td><td>Unavailable</td></tr>"
                       for item, origin in sorted(combined.values(), key=lambda row: ticket_sort_key(row[0])))
        # Current storage has no reliable preparation-usage-to-ticket association.
        # Never substitute the latest chat cost or the zero-cost approval response.
        headers = ("Ticket ID", "Created", "Subject", "Category", "Priority", "Status", "Requester",
                   "Origin", "AI cost to create ticket (USD)")
        head = "".join(f"<th>{title}</th>" for title in headers)
        return page("Admin tickets", NAV + summary + f"<table><tr>{head}</tr>{rows}</table>",
                    status=502 if all_tickets is None and created is None else 200)

    # Exactly two files are ever served; nothing is resolved from the request path.
    video = _first_existing(os.getenv("DEMO_VIDEO_PATH"), root / "demo-assets" / "video.mp4",
                            root / "assets" / "video" / "Nakhla IT Helpdesk portfolio.mp4")
    deck = _first_existing(os.getenv("DEMO_PRESENTATION_PATH"), root / "demo-assets" / "presentation.html",
                           root / "docs" / "IT-Helpdesk-Presenter-v7.html")

    @router.get("/video")
    async def serve_video():
        return FileResponse(video, media_type="video/mp4") if video else Response(status_code=404)

    @router.get("/presentation")
    async def serve_presentation():
        if not deck:
            return Response(status_code=404)
        # sandbox: the deck runs scripts but has no access to this origin or its cookies
        return FileResponse(deck, media_type="text/html", headers={"Content-Security-Policy": "sandbox allow-scripts",
                                                                   "X-Content-Type-Options": "nosniff"})

    return router
