"""Focused offline navigation/guidance/allowlist checks with temporary auth only."""
from html.parser import HTMLParser
import os
import unittest

os.environ.setdefault('GRADIO_ANALYTICS_ENABLED','False')
from app.demo_admin import UPDATES, UPDATE_LIMITS, UPDATES_INTRO
from ui.app_ui import menu_html, PUBLIC_MENU, ADMIN_MENU, ADMIN_LABEL
from tests import test_demo_admin as fixtures


class Elements(HTMLParser):
    def __init__(self,text):
        super().__init__(); self.elements=[]; self.feed(text)
    def handle_starttag(self,tag,attrs): self.elements.append((tag,dict(attrs)))


class NavigationTests(fixtures.DemoAdminBase):
    def setUp(self):
        super().setUp()
        fixtures.DummySimulator.hits.clear()
        self.addCleanup(fixtures.DummySimulator.hits.clear)

    def test_admin_navigation_new_tabs_and_auth_actions_current_tab(self):
        self.admin_login()
        for path in ['/demo/accounts','/demo/tickets','/demo/updates']:
            response=self.client.get(path)
            self.assertEqual(response.status_code,200)
            elements=Elements(response.text).elements
            links=[attrs for tag,attrs in elements if tag=='a']
            self.assertTrue(links)
            for link in links:
                self.assertEqual(link.get('target'),'_blank')
                self.assertEqual(set(link.get('rel','').split()),{'noopener','noreferrer'})
            for tag,attrs in elements:
                if tag=='form': self.assertEqual(attrs.get('target'),'_self')
        self.client.post('/demo/logout')
        login=self.client.get('/demo/login')
        form=next(attrs for tag,attrs in Elements(login.text).elements if tag=='form')
        self.assertEqual(form['target'],'_self')

    def test_protected_account_guidance_and_separate_passwords(self):
        self.assertEqual(self.client.get('/demo/accounts').status_code,303)
        self.admin_login()
        response=self.client.get('/demo/accounts')
        self.assertIn('Choose an employee below, copy their email and password',response.text)
        self.assertLess(response.text.index('Choose an employee'),response.text.index('<table>'))
        link=next(a for tag,a in Elements(response.text).elements if tag=='a' and a.get('href')=='http://localhost:7860')
        self.assertEqual(link['target'],'_blank')
        self.assertEqual(link['rel'],'noopener noreferrer')
        self.assertIn('these logins are separate',response.text)
        self.assertIn('Cache-Control',response.headers)
        self.assertEqual(response.headers['Cache-Control'],'no-store')

    def test_instructor_note_is_exact_prominent_and_has_no_secret(self):
        login=self.client.get('/demo/login')
        self.assertIn('class="instructor-note"',login.text)
        self.assertIn('Instructors: use the demo-admin password shared privately by the developer via WhatsApp. After signing in, choose Demo accounts to obtain an employee login.',login.text)
        self.assertIn('color:#a31313',login.text)
        self.assertNotIn(fixtures.ADMIN_PASSWORD,login.text)
        for account in fixtures.SHEET['accounts']: self.assertNotIn(account['password'],login.text)

    def test_updates_is_fixed_public_information_not_a_directory(self):
        response=self.client.get('/demo/updates')
        self.assertEqual(response.status_code,200)
        for text in [UPDATES_INTRO,*UPDATES,*UPDATE_LIMITS]: self.assertIn(text,response.text)
        self.assertNotIn('data-copy',response.text)
        self.assertNotIn(fixtures.ADMIN_PASSWORD,response.text)
        for path in ['/demo/updates/README.md','/demo/updates/secrets/demo/demo-accounts.json',
                     '/demo/updates/../outside-secret.txt','/demo/secrets/demo-accounts.json']:
            self.assertEqual(self.client.get(path).status_code,404)
        self.assertEqual(self.client.get('/demo/tickets').status_code,303)

    def test_employee_navigation_keeps_resources_and_admin_groups_distinct(self):
        text=menu_html(); elements=Elements(text).elements
        groups=[a for tag,a in elements if tag=='div' and a.get('role')=='group']
        self.assertEqual([g['aria-label'] for g in groups],['Helpdesk resources',ADMIN_LABEL])
        self.assertIn('border:1px solid',groups[1]['style'])
        self.assertIn('flex-wrap:wrap',groups[1]['style'])
        self.assertEqual([label for label,_ in PUBLIC_MENU],['Demo video','Presentation','App health','Updates'])
        self.assertEqual([label for label,_ in ADMIN_MENU],['Admin tickets','Demo accounts'])
        for tag,a in elements:
            if tag=='a': self.assertEqual((a['target'],a['rel']),('_blank','noopener noreferrer'))


if __name__=='__main__': unittest.main()
