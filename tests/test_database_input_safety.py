"""Temporary SQLite/HTTP entry-point checks. No provider or live data access."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.auth import AuthService
from app.approvals import Approvals
from app.main import create_app
from app.retrieval import BudgetLedger
from app.storage import Store
from tests.test_agent_workflow import FakeMCP, FakeRetrieval, ScriptedWorkflow

PAYLOADS = ["' OR '1'='1 --", "' UNION SELECT * FROM employees --", "x'/**/OR/**/1=1--",
    "x'; DROP TABLE employees; --", "x'; UPDATE session_owners SET employee_id='E-2'; --",
    "O'Connor's laptop", "SELECT * FROM Employees WHERE Department = 'Engineering';"]
ROOT = Path(__file__).resolve().parents[1]

def tables(path):
    with closing(sqlite3.connect(path)) as db:
        return db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name").fetchall()

def rows(path, table):
    assert table in {'employees','credentials','admin_credential','sessions','actions','session_owners','spending'}
    with closing(sqlite3.connect(path)) as db:
        return db.execute('SELECT * FROM "'+table+'" ORDER BY 1').fetchall()


class DatabaseInputTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data=Path(self.tmp.name)
        self.auth=AuthService(self.data/'auth.sqlite3',max_failures=100,global_max_failures=1000)
        for ident,email in [('E-1','omar.farah@nakhla.example'),('E-2','sara.mikhail@nakhla.example')]:
            self.auth.provision_employee(ident,email,"O'Connor",'Sales')
            self.auth.set_password(ident,'demo','temporary-test-password')
        self.auth.set_admin_password('temporary-admin-password')
        self.store=Store(self.data/'helpdesk.sqlite3')
        self.mcp=FakeMCP()
        self.mcp.employee={'email':'omar.farah@nakhla.example','department':'Sales'}
        self.approvals=Approvals(self.store,self.mcp)
        self.store.save_session('foreign',{'sentinel':'foreign-state'})
        self.foreign=self.store.propose('foreign',{'sentinel':'foreign-payload'})
        self.auth.claim_session('foreign','E-2')
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':''}):
            self.runtime=ScriptedWorkflow(self.store,self.mcp,FakeRetrieval(),self.approvals,data_dir=self.data,script=[])
        self.client=TestClient(create_app(self.runtime,auth=self.auth),raise_server_exceptions=False)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__,None,None,None)

    def signin(self,email='omar.farah@nakhla.example'):
        r=self.client.post('/api/login',json={'email':email,'password':'temporary-test-password'})
        self.assertEqual(r.status_code,200)
        return {'Authorization':'Bearer '+r.json()['token']}

    def no_database_error(self,response):
        self.assertNotIn(response.status_code,[500,502,503])
        for term in ['sqlite3.','OperationalError','syntax error','no such table','Traceback']:
            self.assertNotIn(term,response.text)

    def integrity(self):
        for name in ['auth.sqlite3','helpdesk.sqlite3']:
            with closing(sqlite3.connect(self.data/name)) as db:
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')

    def test_employee_admin_login_and_tokens_do_not_bypass_authentication(self):
        schema=tables(self.auth.path)
        employees=rows(self.auth.path,'employees')
        credentials=rows(self.auth.path,'credentials')
        for payload in PAYLOADS:
            for email,password in [(payload,'wrong'),('omar.farah@nakhla.example',payload)]:
                r=self.client.post('/api/login',json={'email':email,'password':password})
                self.assertEqual(r.status_code,401)
                self.no_database_error(r)
                self.assertNotIn('token',r.json())
            r=self.client.post('/demo/login',data={'password':payload},follow_redirects=False)
            self.assertEqual(r.status_code,401)
            self.no_database_error(r)
            self.assertFalse(r.headers.get('set-cookie'))
            for header in [{'Authorization':'Bearer '+payload},{'Cookie':'helpdesk_demo_admin='+payload}]:
                r=self.client.get('/api/me',headers=header)
                self.assertEqual(r.status_code,401)
                self.no_database_error(r)
            self.assertIsNone(self.auth.authenticate(payload))
            self.assertFalse(self.auth.authenticate_admin(payload))
            self.client.cookies.set('demo_admin',payload)
            r=self.client.get('/demo/tickets',follow_redirects=False)
            self.assertEqual(r.status_code,303)
            self.assertEqual(r.headers['location'],'/demo/login')
            self.no_database_error(r)
            self.client.cookies.clear()
        self.assertEqual(tables(self.auth.path),schema)
        self.assertEqual(rows(self.auth.path,'employees'),employees)
        self.assertEqual(rows(self.auth.path,'credentials'),credentials)
        self.signin()
        self.integrity()

    def test_http_identifiers_and_foreign_actions_remain_scoped(self):
        headers=self.signin()
        baseline=self.store.get_session('foreign')
        original=self.store.get_action(self.foreign['action_id'])
        self.auth.claim_session('own','E-1')
        for payload in PAYLOADS:
            for body in [dict(session_id=payload,message='hello'),dict(session_id='foreign',message=payload)]:
                r=self.client.post('/api/chat',headers=headers,json=body)
                self.assertIn(r.status_code,[403,422])
                self.no_database_error(r)
            for sid,aid in [('own',payload),(payload,self.foreign['action_id']),('foreign',self.foreign['action_id'])]:
                r=self.client.post('/api/approve',headers=headers,json={'session_id':sid,'action_id':aid,'approved':True})
                self.assertIn(r.status_code,[200,403,422])
                self.assertNotIn('foreign-payload',r.text)
                self.no_database_error(r)
        self.assertEqual(self.store.get_session('foreign'),baseline)
        self.assertEqual(self.store.get_action(self.foreign['action_id']),original)
        self.assertEqual(self.runtime.script_calls,[])
        self.assertEqual(self.mcp.writes,[])
        self.integrity()

    def test_authentication_and_ownership_precede_model_assessment(self):
        r=self.client.post('/api/chat',json={'session_id':'foreign','message':'Help me plan theft'})
        self.assertEqual(r.status_code,401)
        headers=self.signin()
        r=self.client.post('/api/chat',headers=headers,json={'session_id':'foreign','message':'SELECT employees'})
        self.assertEqual(r.status_code,403)
        r=self.client.post('/api/chat',headers=headers,json={'session_id':'own','message':'Help',
            'user':{'email':'sara.mikhail@nakhla.example'}})
        self.assertEqual(r.status_code,403)
        self.assertEqual(self.runtime.script_calls,[])
        self.assertEqual(self.mcp.calls,[])

    def test_chat_payloads_remain_data_through_real_http_and_storage(self):
        headers=self.signin()
        schema=tables(self.store.path)
        original=self.store.get_session('foreign')
        for i,payload in enumerate(PAYLOADS):
            self.runtime.script.append({'action':'retrieve','disposition':'scope','reason':'snippet'})
            r=self.client.post('/api/chat',headers=headers,json={'session_id':f'input-{i}','message':payload})
            self.assertEqual(r.status_code,200)
            self.assertIsNone(r.json()['pending_action'])
            self.no_database_error(r)
            self.assertNotIn('foreign-state',r.text)
        self.assertEqual(tables(self.store.path),schema)
        self.assertEqual(self.store.get_session('foreign'),original)
        self.assertEqual(self.mcp.writes,[])
        self.integrity()

    def test_store_session_action_and_auth_owner_values_are_bound(self):
        schemas={p:tables(p) for p in [self.store.path,self.auth.path]}
        foreign=self.store.get_action(self.foreign['action_id'])
        for payload in PAYLOADS:
            self.assertIsNone(self.store.get_session(payload))
            self.store.save_session(payload,{'text':payload})
            self.assertEqual(self.store.get_session(payload),{'text':payload})
            action=self.store.propose(payload,{'text':payload},summary=payload,fingerprint=payload)
            self.assertEqual(self.store.get_action(action['action_id'])['payload'],{'text':payload})
            self.assertEqual(self.store.latest_action(payload)['action_id'],action['action_id'])
            self.assertEqual(self.store.claim(payload,self.foreign['action_id'])[0],'unknown_action')
            self.assertFalse(self.store.reject(payload,self.foreign['action_id']))
            self.assertIsNone(self.store.reopen(payload,self.foreign['action_id']))
            self.assertIsNone(self.store.get_action(payload))
            self.assertFalse(self.auth.owns_session(payload,'E-2'))
            self.assertTrue(self.auth.claim_session(payload,'E-1'))
            self.assertFalse(self.auth.claim_session(payload,'E-2'))
            self.assertTrue(self.auth.owns_session(payload,'E-1'))
            self.store.supersede(payload)
        self.assertEqual(self.store.get_action(self.foreign['action_id']),foreign)
        for path,schema in schemas.items(): self.assertEqual(tables(path),schema)
        self.integrity()

    def test_ledger_fields_are_bound_and_spending_is_not_erased(self):
        ledger=BudgetLedger(self.data,ceiling=2.5)
        schema=tables(ledger.path)
        for payload in PAYLOADS:
            ident=ledger.reserve(.000001,payload)
            ledger.settle(ident,.000001)
            with self.assertRaises(ValueError): ledger.settle(payload,0)
        self.assertEqual(ledger.snapshot()['calls'],len(PAYLOADS))
        self.assertEqual(tables(ledger.path),schema)
        with closing(sqlite3.connect(ledger.path)) as db:
            self.assertEqual(sorted(r[0] for r in db.execute('SELECT kind FROM spending')),sorted(PAYLOADS))

    def test_real_maintenance_cli_noop_and_explicit_apply_use_disposable_copy(self):
        old=self.store.propose('expired',{'text':PAYLOADS[3]})
        pending=self.store.propose('pending',{'text':PAYLOADS[0]})
        with self.store.connect() as db:
            db.execute("UPDATE actions SET status='succeeded',created=1 WHERE id=?",(old['action_id'],))
            db.execute('UPDATE sessions SET updated=1 WHERE id=?',('foreign',))
        before=rows(self.store.path,'actions')
        command=[sys.executable,'-B',str(ROOT/'scripts/maintain_history.py'),'--data-dir',str(self.data)]
        proc=subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(proc.returncode,0)
        self.assertEqual(rows(self.store.path,'actions'),before)
        proc=subprocess.run(command+['--apply'],capture_output=True,text=True)
        self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertIsNone(self.store.get_action(old['action_id']))
        self.assertEqual(self.store.get_action(pending['action_id'])['status'],'pending')
        self.integrity()


if __name__ == '__main__':
    unittest.main()
