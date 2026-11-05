"""Isolated browser checks; project Python -B, already-installed Playwright/Chromium only."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
# Reuse the existing same-Python-version browser package without installing into this project.
sys.path.append(str(Path.home() / 'Chatterbox-Test/.venv/Lib/site-packages'))
from tests.browser import ui_smoke as smoke
from tests.ui_fixtures import ORDER, HEADERS
from playwright.sync_api import sync_playwright, expect

smoke.OUT = ROOT / 'evidence/ui-enhancements-2026-11-04'
smoke.APP_PORT, smoke.SIM_PORT, smoke.UI_PORT = 8135, 8136, 7875
smoke.APP, smoke.UI = 'http://127.0.0.1:8135', 'http://127.0.0.1:7875'


def check_usage(page):
    page.goto(smoke.UI)
    page.get_by_label('Work email').fill(smoke.ONE[0])
    page.get_by_label('Password').fill(smoke.ONE[1])
    page.get_by_role('button', name='Sign in', exact=True).click()
    expect(page.get_by_text('Signed in as').first).to_be_visible()
    for fixture, expected_text in [('confirmed', 'Confirmed cost (USD): 0.00300000'),
                                    ('estimated', 'Estimated cost (USD): 0.00200000'),
                                    ('unknown', 'Cost (USD): Unknown (final billing incomplete)'),
                                    ('missing', 'Cost (USD): Unknown')]:
        smoke.say(page, 'fixture-' + fixture)
        expect(page.get_by_text('[stub] tester.one@nakhla.example wrote: fixture-' + fixture).first).to_be_visible()
        expect(page.get_by_text(expected_text, exact=False).first).to_be_visible()
        headings = page.locator('h3').all_text_contents()
        smoke.check('usage below tool calls: ' + fixture,
                    headings.index('Last-turn usage') > headings.index('Tool calls (last turn)'))
        if fixture == 'missing':
            body = page.locator('body').inner_text()
            smoke.check('missing usage clears prior costs/tokens',
                        'Input tokens: Unknown' in body and 'Output tokens: Unknown' in body
                        and 'Confirmed cost (USD)' not in body and 'Unknown usage reservation' not in body)
        if fixture == 'unknown':
            smoke.check('unknown reservation is not shown as a charge',
                        'not a confirmed charge' in page.locator('body').inner_text())
            page.screenshot(path=str(smoke.OUT / 'usage-unknown.png'))
    page.get_by_role('button', name='Sign out', exact=True).click()


def check_table(context):
    page = context.new_page()
    page.goto(smoke.APP + '/demo/login')
    page.get_by_label('Demo admin password').fill(smoke.ADMIN)
    page.get_by_role('button', name='Sign in', exact=True).click()
    page.wait_for_url('**/demo/accounts')
    page.goto(smoke.APP + '/demo/tickets')
    smoke.check('ticket table headers', page.locator('th').all_text_contents() == HEADERS)
    rows = page.locator('tr').all()[1:]
    smoke.check('status groups and newest first', [r.locator('td').first.inner_text() for r in rows] == ORDER)
    smoke.check('one nine-column row per ticket; no false cost attribution', len(rows) == len(ORDER)
                and all(r.locator('td').count() == 9 and r.locator('td').last.inner_text() == 'Unavailable' for r in rows))
    smoke.check('ticket text cannot execute markup', page.evaluate('window.ticketXss') is None
                and page.locator('td').filter(has_text='<script>window.ticketXss=1</script>').count() == 1)
    smoke.check('admin menu order', page.locator('nav a').all_text_contents() ==
                ['Demo video', 'Presentation', 'Admin tickets', 'App health', 'Demo accounts'])
    page.screenshot(path=str(smoke.OUT / 'admin-tickets.png'))


def main():
    smoke.OUT.mkdir(parents=True, exist_ok=True)
    servers = smoke.start_servers()
    try:
        with sync_playwright() as playwright:
            executable = os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE', str(Path.home() /
                'AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe'))
            browser = playwright.chromium.launch(executable_path=executable, headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(30000)
            smoke.run_employee_ui(page)
            smoke.run_admin_pages(context)
            check_usage(page)
            check_table(context)
            browser.close()
    finally:
        for process in servers:
            process.terminate()
        for process in servers:
            try:
                process.wait(timeout=10)
            except smoke.subprocess.TimeoutExpired:
                process.kill()
    failed = sum(not ok for _, ok, _ in smoke.results)
    report = [f'{len(smoke.results) - failed} passed; {failed} failed', ''] + [
        f'{"PASS" if ok else "FAIL"}: {name}' for name, ok, _ in smoke.results]
    (smoke.OUT / 'browser-results.txt').write_text('\n'.join(report) + '\n')
    return int(bool(failed))


if __name__ == '__main__':
    raise SystemExit(main())
