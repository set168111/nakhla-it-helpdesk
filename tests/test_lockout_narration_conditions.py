"""Offline SP-001/KB-006 narration regression; no provider, services or real data."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.agent import lockout_escalation_narration_error, report_policy
from app.approvals import Approvals
from app.storage import Store
from tests.test_agent_workflow import CHUNK, EMPLOYEE, FakeMCP, FakeRetrieval, ScriptedWorkflow

BAD = ('Repeated lockouts may indicate an old password saved on a device or a possible '
       'password-guessing attack, which requires reporting to Security Operations with category security and priority P2.')
GOOD = ('Repeated lockouts can come from a device using an old saved password. '
        'If you have three or more lockouts in one day without a known cause, '
        'report them to Security Operations (category security, priority P2).')
OK = {'accepted': True, 'complete': True}
ATTEMPT = 'I tried restarting my browser.'


def claim(text):
    return {'text': text, 'chunk_ids': [CHUNK['chunk_id']]}


class NarrationRuleTests(unittest.TestCase):
    def test_missing_conditions_are_detected_individually_and_in_the_reported_sentence(self):
        for text in [BAD,
                     'Unexplained lockouts in one day require reporting to Security Operations at P2.',
                     'Three unexplained lockouts require reporting to Security Operations at P2.',
                     'Three lockouts in one day require reporting to Security Operations at P2.']:
            with self.subTest(text=text):
                self.assertTrue(lockout_escalation_narration_error(text))

    def test_valid_threshold_paraphrases_and_ordinary_guidance_are_preserved(self):
        for text in [GOOD,
                     'Three unexplained daily lockouts require Security Operations escalation at P2.',
                     'Locked three or more times in one day and cannot find an old password anywhere: report to Security Operations at P2.',
                     'Three lockouts today without a known cause may be an attack; report to Security Operations at P2.',
                     'Repeated lockouts often mean a saved old password; update or remove it, then unlock.',
                     'An ordinary lockout does not require reporting to Security Operations at P2.',
                     'Wait 30 minutes or unlock with NakhlaKey.',
                     'A lockout is separate from entering a password on a suspicious page; report that compromise to Security Operations at P1.']:
            with self.subTest(text=text):
                self.assertFalse(lockout_escalation_narration_error(text))

    def test_ticket_routing_remains_conditional_not_all_repeated_lockouts(self):
        for issue in ['My account locked twice today without a known cause.',
                      'My account locked three times last month without a known cause.',
                      'My account locked three times today because my phone uses an old password.']:
            self.assertNotEqual(report_policy(EMPLOYEE, issue)[0]['category'], 'security')
        policy, _ = report_policy(EMPLOYEE, 'My account locked three times today without a known cause.')
        self.assertEqual((policy['category'], policy['priority']), ('security', 'P2'))


class NarrationWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.store = Store(self.data / 'state.sqlite3')
        self.mcp = FakeMCP()
        self.approvals = Approvals(self.store, self.mcp)
        self.retrieval = FakeRetrieval()
        source = (Path(__file__).resolve().parents[1] / 'dataset/knowledge_base/KB-006-account-lockout.md').read_text(encoding='utf-8')
        self.retrieval.chunks = [{**copy.deepcopy(CHUNK), 'text': source}]

    def workflow(self, *script):
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': ''}):
            return ScriptedWorkflow(self.store, self.mcp, self.retrieval, self.approvals,
                                    data_dir=self.data, script=script)

    async def test_case17_narration_is_corrected_without_reclassifying_its_identity_draft(self):
        draft = {'intent': 'draft', 'subject': 'NakhlaID login unavailable', 'description': 'Login unavailable.',
                 'attempted_steps': [ATTEMPT], 'claims': [claim(BAD)], 'affected_users': 1}
        workflow = self.workflow({'action': 'retrieve'}, draft, {'claims': [claim(GOOD)]}, OK)
        messages = ['Unbale to login, create a ticket', 'completely blocked', 'no workaroud',
                    'no workaround', 'NakhlaID shows NID-423', ATTEMPT]
        for message in messages:
            result = await workflow.chat('case17', message, {'email': EMPLOYEE['email']})
        self.assertEqual(result['state'], 'await_confirmation', result['reply'])
        self.assertIn(GOOD, result['reply'])
        self.assertNotIn(BAD, result['reply'])
        self.assertEqual((result['pending_action']['payload']['category'], result['pending_action']['payload']['priority']),
                         ('identity_access', 'P2'))
        self.assertEqual(result['pending_action']['payload']['attempted_steps'], [ATTEMPT])
        self.assertIn('lockout_conditions_guard', (self.data / 'traces.jsonl').read_text())
        self.assertEqual([schema for _, schema, _ in workflow.script_calls].count('ClaimsRevision'), 1)
        self.assertEqual(self.mcp.writes, [])

    async def test_uncorrected_overbroad_narration_fails_closed_before_draft_or_write(self):
        workflow = self.workflow({'action': 'retrieve'}, {'intent': 'answer', 'claims': [claim(BAD)]},
                                 {'claims': [claim(BAD)]})
        result = await workflow.chat('bad', 'My NakhlaID keeps locking. What should I do?', {'email': EMPLOYEE['email']})
        self.assertEqual(result['state'], 'unverified')
        self.assertIsNone(result['pending_action'])
        self.assertNotIn(BAD, result['reply'])
        self.assertFalse(any(role == 'Reviewer' for role, _, _ in workflow.script_calls))
        self.assertEqual(self.mcp.writes, [])

    async def test_ordinary_unlock_guidance_does_not_trigger_escalation_or_revision(self):
        ordinary = ('Repeated lockouts often come from an old saved password. Update or remove it, then unlock. '
                    'An ordinary lockout does not require reporting to Security Operations at P2.')
        workflow = self.workflow({'action': 'retrieve'}, {'intent': 'answer', 'claims': [claim(ordinary)]}, OK)
        result = await workflow.chat('ordinary', 'My NakhlaID keeps locking. What should I do?', {'email': EMPLOYEE['email']})
        self.assertEqual(result['state'], 'answer')
        self.assertIn(ordinary, result['reply'])
        self.assertIsNone(result['pending_action'])
        self.assertEqual([schema for _, schema, _ in workflow.script_calls].count('ClaimsRevision'), 0)
        self.assertEqual(self.mcp.writes, [])
