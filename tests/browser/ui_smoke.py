"""OPT-IN isolated browser smoke test (not part of the unittest suite).

Starts an ISOLATED stack (stub chat runtime + real create_app/auth, real Gradio UI) on loopback ports,
drives it with Playwright and writes evidence. No installations: use an interpreter that already has
Playwright and its browser, e.g. the existing Chatterbox environment:

    .venv/Scripts/python.exe -B tests/browser/ui_smoke.py

The project interpreter starts the servers. Never touches the running stack, real secrets or live data.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
PROJECT_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
APP_PORT, SIM_PORT, UI_PORT = 8131, 8132, 7871
APP, UI = f"http://127.0.0.1:{APP_PORT}", f"http://127.0.0.1:{UI_PORT}"
OUT = ROOT / "evidence" / "auth-batch-2026-11-04"
ONE = ("tester.one@nakhla.example", "throwaway-test-password-1")
ADMIN = "throwaway-admin-password"
results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, bool(condition), detail))
    print(("PASS " if condition else "FAIL ") + name + (f" - {detail}" if detail and not condition else ""))


def wait_http(url: str, seconds: float = 90) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except Exception:
            time.sleep(0.5)
    raise SystemExit("server did not start: " + url)


def start_servers() -> list[subprocess.Popen]:
    base = {**os.environ, "ISO_APP_PORT": str(APP_PORT), "ISO_SIM_PORT": str(SIM_PORT), "PYTHONDONTWRITEBYTECODE": "1",
            "OPENROUTER_API_KEY": ""}
    app = subprocess.Popen([str(PROJECT_PYTHON), "-B", str(ROOT / "tests/browser/serve_isolated_app.py")], env=base, cwd=ROOT)
    ui_env = {**base, "APP_URL": APP, "APP_PUBLIC_URL": APP, "UI_PORT": str(UI_PORT), "UI_HOST": "127.0.0.1",
              "GRADIO_ANALYTICS_ENABLED": "False"}
    ui = subprocess.Popen([str(PROJECT_PYTHON), "-B", str(ROOT / "ui/app_ui.py")], env=ui_env, cwd=ROOT)
    wait_http(APP + "/demo/login")
    wait_http(UI)
    return [app, ui]


def say(page, text: str) -> None:
    page.get_by_label("Message", exact=True).fill(text)
    page.get_by_label("Message", exact=True).press("Enter")


def run_employee_ui(page) -> None:
    page.goto(UI)
    expect(page.get_by_text("LOCAL DEMO ONLY").first).to_be_visible(timeout=60000)
    menu = {a.inner_text(): (a.get_attribute("href"), a.get_attribute("target"), a.get_attribute("rel"))
            for a in page.locator("a[href^='%s/']" % APP).all()}
    for label, path in (("Demo accounts", "/demo/login"), ("Admin tickets", "/demo/tickets"), ("App health", "/health"),
                        ("Demo video", "/demo/video"), ("Presentation", "/demo/presentation")):
        check(f"menu link: {label}", menu.get(label, (None,))[0] == APP + path, str(menu.get(label)))
    check("menu links open in a new tab safely", len(menu) == 5 and all(t == "_blank" and "noopener" in (r or "") for _, t, r in menu.values()))
    check("starts signed out", page.get_by_text("Not signed in.").first.is_visible())
    say(page, "hello before sign in")
    expect(page.get_by_text("Please sign in first.").first).to_be_visible(timeout=20000)
    check("message before sign-in is refused", True)
    page.get_by_label("Work email").fill(ONE[0])
    page.get_by_label("Password").fill("definitely-wrong")
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_text("Invalid email or password.").first).to_be_visible(timeout=20000)
    check("wrong password gives the generic failure", True)
    check("password box is cleared after a failed sign-in", page.get_by_label("Password").input_value() == "")
    page.get_by_label("Password").fill(ONE[1])
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_text("Signed in as").first).to_be_visible(timeout=20000)
    shown = page.get_by_text("Signed in as").first.inner_text()
    check("signed-in identity is displayed read-only", "Tester One" in shown and ONE[0] in shown and "Support" in shown, shown)
    check("password is cleared after sign-in", page.get_by_label("Password").input_value() == "")
    say(page, "my printer is broken")
    expect(page.get_by_text("[stub] tester.one@nakhla.example wrote: my printer is broken").first).to_be_visible(timeout=30000)
    check("chat reply carries the verified identity (no email was typed in the chat)", True)
    page.screenshot(path=str(OUT / "ui-signed-in.png"))
    page.get_by_role("button", name="Sign out").click()
    expect(page.get_by_text("Signed out.").first).to_be_visible(timeout=20000)
    check("sign out shows the signed-out state", page.get_by_text("Not signed in.").first.is_visible())
    say(page, "after sign out")
    expect(page.get_by_text("Please sign in first.").first).to_be_visible(timeout=20000)
    check("chat after sign-out needs a new sign-in", True)


def run_admin_pages(context) -> None:
    page = context.new_page()
    page.goto(APP + "/demo/accounts")
    check("accounts page redirects to the admin login", page.url.endswith("/demo/login"), page.url)
    page.get_by_label("Demo admin password").fill("wrong-admin")
    page.get_by_role("button", name="Sign in").click()
    check("wrong admin password is refused generically", "Invalid demo admin password." in page.content())
    page.get_by_label("Demo admin password").fill(ADMIN)
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url("**/demo/accounts")
    check("accounts page is labelled LOCAL DEMO ONLY", "LOCAL DEMO ONLY" in page.content())
    check("copy buttons exist for emails and passwords",
          page.get_by_role("button", name="Copy email").count() == 2 and page.get_by_role("button", name="Copy password").count() == 2)
    context.grant_permissions(["clipboard-read", "clipboard-write"], origin=APP)
    page.get_by_role("button", name="Copy email").first.click()
    check("copy email puts the address on the clipboard", page.evaluate("navigator.clipboard.readText()") == ONE[0])
    page.get_by_role("button", name="Copy password").first.click()
    check("copy password puts the password on the clipboard", page.evaluate("navigator.clipboard.readText()") == ONE[1])
    check("passwords are not shown as text", ONE[1] not in page.locator("body").inner_text())
    page.screenshot(path=str(OUT / "demo-accounts-admin.png"))
    page.goto(APP + "/demo/tickets")
    check("admin tickets page lists simulator tickets", "IT-2001" in page.content() and "Isolated browser test ticket" in page.content())
    # the page CSP (default-src none) also blocks fetch() from the admin page itself; use the browser context
    # request API, which shares the browser cookies
    status = context.request.post(APP + "/api/chat", data={"session_id": "x", "message": "hi"}).status
    check("admin session does not authenticate /api/chat", status == 401, str(status))
    page.get_by_role("button", name="Sign out").click()
    page.goto(APP + "/demo/accounts")
    check("admin sign-out ends the session", page.url.endswith("/demo/login"), page.url)
    for path, expected in (("/demo/video", "video/mp4"), ("/demo/presentation", "text/html")):
        reply = context.request.get(APP + path)
        check(f"{path} is served", reply.status == 200 and expected in reply.headers.get("content-type", ""))
    check("no static route exposes the credential sheet", context.request.get(APP + "/secrets/demo/demo-accounts.json").status == 404)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    servers = start_servers()
    try:
        with sync_playwright() as p:
            # An already-installed Chromium may differ from the build this Playwright expects; pass its path
            # through PLAYWRIGHT_CHROMIUM_EXECUTABLE instead of installing anything.
            executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
            browser = p.chromium.launch(executable_path=executable) if executable else p.chromium.launch()
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(30000)
            run_employee_ui(page)
            run_admin_pages(context)
            browser.close()
    finally:
        for proc in servers:
            proc.terminate()
        for proc in servers:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
    failed = [r for r in results if not r[1]]
    lines = ["# Isolated browser smoke test (Playwright, stub runtime, throwaway test accounts)", "",
             f"{len(results) - len(failed)} passed, {len(failed)} failed", ""]
    lines += [f"- {'PASS' if ok else 'FAIL'}: {name}" for name, ok, _ in results]
    (OUT / "browser-smoke.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
