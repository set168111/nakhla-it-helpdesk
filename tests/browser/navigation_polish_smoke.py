"""Isolated real browser/UI/auth checks; existing Playwright/Chromium, stub answers only."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
sys.path.append(os.environ.get('PLAYWRIGHT_SITE_PACKAGES',str(Path.home()/'Chatterbox-Test/.venv/Lib/site-packages')))
from playwright.sync_api import sync_playwright, expect
from tests.browser import ui_enhancements_smoke as prior
from app.demo_admin import UPDATES_INTRO, UPDATES, UPDATE_LIMITS
from ui.app_ui import ADMIN_LABEL

smoke=prior.smoke
OUT=ROOT/'evidence/navigation-polish-2026-11-05/browser'
PYTHON=ROOT/'.venv/Scripts/python.exe'

def free(avoid=()):
    for port in range(18220,18260):
        if port in avoid: continue
        with socket.socket() as sock:
            try: sock.bind(('127.0.0.1',port))
            except OSError: continue
            return port
    raise RuntimeError('No isolated browser port available')

def check(name,value):
    smoke.check(name,value)
    assert value,name

def run():
    OUT.mkdir(parents=True,exist_ok=True)
    appport=free(); simport=free({appport}); uiport=free({appport,simport})
    smoke.APP_PORT,smoke.SIM_PORT,smoke.UI_PORT=appport,simport,uiport
    smoke.APP,smoke.UI=f'http://127.0.0.1:{appport}',f'http://127.0.0.1:{uiport}'
    smoke.OUT=OUT
    tmp=Path(tempfile.mkdtemp(prefix='nav-polish-browser-')).resolve()
    (tmp/'owner.json').write_text(json.dumps({'purpose':'navigation-polish-browser','root':str(tmp)}))
    fixture=tmp/'fixtures'; fixture.mkdir()
    env={**os.environ,'ISO_APP_PORT':str(appport),'ISO_SIM_PORT':str(simport),
         'ISO_FIXTURE_DIR':str(fixture),'OPENROUTER_API_KEY':'','PYTHONDONTWRITEBYTECODE':'1',
         'HELPDESK_API_KEY':'synthetic-isolated-key','APP_DATA_DIR':str(tmp/'state'),
         'GRADIO_ANALYTICS_ENABLED':'False'}
    servers=[]; logs=[]; blocked=[]; intercepted=[]
    try:
        flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
        for name,args,extra in [
            ('app',[str(PYTHON),'-B',str(ROOT/'tests/browser/serve_isolated_app.py')],{}),
            ('ui',[str(PYTHON),'-B',str(ROOT/'ui/app_ui.py')],{'APP_URL':smoke.APP,'APP_PUBLIC_URL':smoke.APP,'UI_PORT':str(uiport),'UI_HOST':'127.0.0.1'})]:
            log=(tmp/(name+'.log')).open('w',encoding='utf-8'); logs.append(log)
            servers.append(subprocess.Popen(args,cwd=ROOT,env={**env,**extra},stdout=log,stderr=subprocess.STDOUT,creationflags=flags))
        (OUT/'run-state.json').write_text(json.dumps({'temporary_root':str(tmp),'owned_launcher_pids':[p.pid for p in servers],
            'ports':[appport,simport,uiport],'contains_no_credentials':True},indent=2))
        smoke.wait_http(smoke.APP+'/demo/login'); smoke.wait_http(smoke.UI)
        with sync_playwright() as p:
            executable=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE',str(Path.home()/'AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe'))
            browser=p.chromium.launch(executable_path=executable,headless=True)
            context=browser.new_context(viewport={'width':1280,'height':900})
            def routing(route):
                url=route.request.url
                if url.startswith('http://localhost:7860'):
                    intercepted.append(url); route.fulfill(status=200,body='Isolated employee-link target; no working-stack request'); return
                if any(url.startswith(base+'/') for base in [smoke.APP,smoke.UI,f'http://127.0.0.1:{simport}']): route.continue_()
                else: blocked.append(url.split('?',1)[0]); route.abort()
            context.route('**/*',routing)
            page=context.new_page(); page.set_default_timeout(30000); page.goto(smoke.UI)
            resources=page.get_by_role('group',name='Helpdesk resources',exact=True)
            admins=page.get_by_role('group',name=ADMIN_LABEL,exact=True)
            expect(resources).to_be_visible(); expect(admins).to_be_visible()
            check('public resource group order',resources.get_by_role('link').all_text_contents()==['Demo video','Presentation','App health','Updates'])
            check('bordered administrator group only contains admin links',admins.get_by_role('link').all_text_contents()==['Admin tickets','Demo accounts'])
            check('administrator border rendered',admins.evaluate("e => parseFloat(getComputedStyle(e).borderTopWidth) >= 1"))
            page.screenshot(path=str(OUT/'employee-desktop.png'))
            for width in [360,320]:
                page.set_viewport_size({'width':width,'height':900})
                box=admins.bounding_box(); nav=page.get_by_role('navigation',name='Helpdesk links').bounding_box()
                check('employee navigation fits '+str(width)+'px',box['x']>=0 and box['x']+box['width']<=width+1 and nav['x']+nav['width']<=width+1)
                page.screenshot(path=str(OUT/f'employee-mobile-{width}.png'))
            page.set_viewport_size({'width':1280,'height':900})
            parent=page.url
            with page.expect_popup() as event: resources.get_by_role('link',name='Updates',exact=True).click()
            updates=event.value; updates.wait_for_load_state('domcontentloaded')
            check('employee Updates opens a safe new tab',page.url==parent and updates.evaluate('window.opener === null') and updates.evaluate('document.referrer')=='')
            for text in [UPDATES_INTRO,*UPDATES,*UPDATE_LIMITS]: expect(updates.get_by_text(text,exact=True)).to_be_visible()
            check('updates lists verified improvements and limitations',True)
            updates.screenshot(path=str(OUT/'updates.png')); updates.close()
            # Existing signed-in/clipboard/usage/table regressions, all stubbed offline.
            smoke.run_employee_ui(page)
            smoke.run_admin_pages(context)
            prior.check_usage(page)
            prior.check_table(context)
            admin=context.new_page(); admin.goto(smoke.APP+'/demo/login')
            # check_table left the shared admin cookie signed in; end ONLY this synthetic session.
            context.request.post(smoke.APP+'/demo/logout')
            admin.goto(smoke.APP+'/demo/login')
            note=admin.get_by_text('Instructors: use the demo-admin password shared privately by the developer via WhatsApp. After signing in, choose Demo accounts to obtain an employee login.',exact=True)
            expect(note).to_be_visible()
            check('instructor note renders prominently red',note.evaluate("e => getComputedStyle(e).color === 'rgb(163, 19, 19)' && parseFloat(getComputedStyle(e).borderLeftWidth) >= 4"))
            admin.screenshot(path=str(OUT/'admin-signin.png'))
            count=len(context.pages); admin.get_by_label('Demo admin password').fill(smoke.ADMIN)
            admin.get_by_role('button',name='Sign in',exact=True).click(); admin.wait_for_url('**/demo/accounts')
            check('admin sign-in stays in current tab',len(context.pages)==count)
            expect(admin.get_by_text('Choose an employee below, copy their email and password, then open the',exact=False)).to_be_visible()
            check('guidance before employee credential table',admin.locator('p').filter(has_text='Choose an employee below').evaluate("e => !!(e.compareDocumentPosition(document.querySelector('table')) & Node.DOCUMENT_POSITION_FOLLOWING)"))
            check('separate admin/employee login guidance',admin.get_by_text('these logins are separate.',exact=False).is_visible())
            for a in admin.locator('nav a').all():
                check('admin new-tab attributes: '+a.inner_text(),a.get_attribute('target')=='_blank' and set(a.get_attribute('rel').split())=={'noopener','noreferrer'})
            before=admin.url
            with admin.expect_popup() as event: admin.get_by_role('link',name='Updates',exact=True).click()
            popup=event.value; popup.wait_for_load_state('domcontentloaded')
            check('admin Updates opens new tab without opener/referrer',admin.url==before and popup.evaluate('window.opener === null') and popup.evaluate('document.referrer')==''); popup.close()
            employee=admin.get_by_role('link',name='Employee sign-in',exact=True)
            check('Employee sign-in URL is fixed requested localhost URL',employee.get_attribute('href')=='http://localhost:7860')
            with admin.expect_popup() as event: employee.click()
            popup=event.value; popup.wait_for_load_state('domcontentloaded')
            check('Employee sign-in opens safe intercepted tab, never working stack',popup.evaluate('window.opener === null') and 'Isolated employee-link target' in popup.content() and len(intercepted)==1); popup.close()
            admin.screenshot(path=str(OUT/'admin-accounts.png'))
            count=len(context.pages); admin.get_by_role('button',name='Sign out',exact=True).click(); admin.wait_for_url('**/demo/login')
            check('admin sign-out stays in current tab',len(context.pages)==count)
            for path in ['/demo/accounts','/demo/tickets']:
                check('protected after logout: '+path,context.request.get(smoke.APP+path,max_redirects=0).status==303)
            check('new public Updates does not expose credential tree',context.request.get(smoke.APP+'/demo/updates/secrets/demo-accounts.json').status==404)
            check('updates public while admin tables remain protected',context.request.get(smoke.APP+'/demo/updates').status==200)
            browser.close()
    finally:
        for process in servers:
            if process.poll() is None:
                if os.name=='nt':
                    subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
                else: process.terminate()
        for process in servers:
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
        for log in logs: log.close()
        assert tmp.is_relative_to(Path(tempfile.gettempdir()).resolve()) and tmp.name.startswith('nav-polish-browser-')
        assert json.loads((tmp/'owner.json').read_text())=={'purpose':'navigation-polish-browser','root':str(tmp)}
        import shutil
        for attempt in range(20):
            try: shutil.rmtree(tmp); break
            except PermissionError:
                if attempt==19: raise
                time.sleep(.25)
        failed=[name for name,ok,_ in smoke.results if not ok]
        (OUT/'results.json').write_text(json.dumps({'passed':len(smoke.results)-len(failed),'failed':failed,
            'checks':[{'name':n,'passed':ok} for n,ok,_ in smoke.results],
            'provider_calls':0,'runtime':'real HTTP/auth/Gradio; stub chat/simulator and throwaway fixtures',
            'browser':'existing Chromium 1243 / existing Playwright via project Python -B',
            'working_employee_link_intercepted':len(intercepted),'nonlocal_browser_requests_blocked':len(blocked),
            'own_servers_and_temporary_credentials_removed':True},indent=2),encoding='utf-8')
    assert not failed
    print(f'{len(smoke.results)} isolated browser checks passed; no provider or working-stack requests')

if __name__=='__main__': run()
