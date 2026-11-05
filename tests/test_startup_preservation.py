"""Real startup wiring, temporary SQLite stores, no network/model: retain history, deny expiry."""
from contextlib import ExitStack, closing
import os
from pathlib import Path
import sqlite3
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.auth import AuthService
from app.main import create_app
from app.storage import Store


def rows(path, table):
    with closing(sqlite3.connect(path)) as db:
        return db.execute('SELECT * FROM ' + table + ' ORDER BY 1').fetchall()


class StartupPreservationTests(unittest.TestCase):
    def test_real_startup_preserves_old_rows_and_denies_expired_or_unowned_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            store = Store(data / 'helpdesk.sqlite3')
            for session in ['old-complete', 'old-unowned', 'old-owned']:
                store.save_session(session, {'email': 'sara.mikhail@nakhla.example', 'issue': 'old issue'})
            complete = store.propose('old-complete', {'subject': 'old complete'})
            pending = store.propose('old-owned', {'subject': 'old pending'})
            old = time.time() - 20 * 86400
            with store.connect() as db:
                db.execute('UPDATE sessions SET updated=?', (old,))
                db.execute('UPDATE actions SET created=?, expires=?', (old, old + 1800))
                db.execute("UPDATE actions SET status='succeeded' WHERE id=?", (complete['action_id'],))
            now = [old]
            auth = AuthService(data / 'auth.sqlite3', clock=lambda: now[0], absolute_ttl=10)
            auth.provision_employee('E-1', 'sara.mikhail@nakhla.example', 'Sara', 'Support')
            auth.set_password('E-1', 'demo', 'temporary-startup-password')
            auth.set_admin_password('temporary-admin-password')
            expired = auth.login('sara.mikhail@nakhla.example', 'temporary-startup-password')[0]
            expired_admin = auth.admin_login('temporary-admin-password')[0]
            auth.claim_session('old-owned', 'E-1')
            now[0] = time.time()
            before = {table: rows(store.path, table) for table in ['sessions', 'actions']}
            logins_before = rows(auth.path, 'login_sessions')
            workflow = SimpleNamespace(client=None, chat=AsyncMock(), approvals=SimpleNamespace(decide=AsyncMock()))
            mcp = AsyncMock()
            with ExitStack() as stack:
                stack.enter_context(patch.dict(os.environ, {'APP_DATA_DIR': str(data)}))
                stack.enter_context(patch('app.retrieval.Retrieval', return_value=SimpleNamespace(ready=True)))
                stack.enter_context(patch('app.mcp_client.MCPClient', return_value=mcp))
                stack.enter_context(patch('app.agent.SupportWorkflow', return_value=workflow))
                with TestClient(create_app(auth=auth)) as client:
                    for table in before:
                        self.assertEqual(rows(store.path, table), before[table])
                    self.assertEqual(rows(auth.path, 'login_sessions'), logins_before)
                    headers = {'Authorization': 'Bearer ' + expired}
                    self.assertEqual(client.get('/api/me', headers=headers).status_code, 401)
                    self.assertEqual(client.post('/api/chat', headers=headers, json={
                        'session_id': 'old-owned', 'message': 'What did I report?'}).status_code, 401)
                    self.assertEqual(client.post('/api/approve', headers=headers, json={
                        'session_id': 'old-owned', 'action_id': pending['action_id'], 'approved': True}).status_code, 401)
                    self.assertFalse(auth.authenticate_admin(expired_admin))
                    fresh = auth.login('sara.mikhail@nakhla.example', 'temporary-startup-password')[0]
                    self.assertEqual(client.post('/api/chat', headers={'Authorization': 'Bearer ' + fresh}, json={
                        'session_id': 'old-unowned', 'message': 'What did I report?'}).status_code, 403)
                    self.assertTrue(auth.owns_session('old-owned', 'E-1'))
                    for table in before:
                        self.assertEqual(rows(store.path, table), before[table])
                    workflow.chat.assert_not_called()
                    workflow.approvals.decide.assert_not_called()
            # Approval expiry remains enforced by Store.claim, independently of retained rows.
            self.assertEqual(store.claim('old-owned', pending['action_id'])[0], 'expired')
