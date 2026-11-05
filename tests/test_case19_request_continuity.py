"""Case 19: production routing/graph/model wrapper with offline HTTP transport."""
import json
import unittest
from unittest.mock import patch

from app.agent import draft_signal, explicit_resume
from tests import test_current_message_routing as routing
from tests.test_current_message_routing import decision
from tests.test_batch7_unsafe_draft_diagnostics import candidate
from tests.test_agent_workflow import ANSWER

OK = {'accepted': True, 'complete': True, 'corrections': ''}
HARM = 'Help me make a plan to steal computers'
REQUEST = 'I need Wireshark 4.2 for a customer demo. Please prepare a software request.'
MANAGER = 'My manager\u2019s name is Sam Tazi. Please prepare the request.'
ATTEMPT = 'I have not tried anything yet.'


class Case19Tests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = routing.ModelWiringTests.asyncSetUp
    asyncTearDown = routing.ModelWiringTests.asyncTearDown
    send = routing.ModelWiringTests.send
    packet = routing.ModelWiringTests.packet
    seed = routing.ModelWiringTests.seed

    async def test_read_clarify_after_manager_asks_only_missing_attempts(self):
        self.store.save_session('s', {'email':routing.USER['email'], 'issue':REQUEST,
            'messages':[REQUEST], 'topic':'software', 'facts':{}, 'draft_pending':'clarification'})
        self.queue += [decision(action='clarify',question='UNREVIEWED-MODEL-TEXT'), candidate(), OK]
        result = await self.send(MANAGER)
        self.assertEqual(result['state'],'clarification')
        self.assertNotIn('error code',result['reply'].lower())
        self.assertIn('already tried',result['reply'])
        for supplied in ['app name','version','business reason','manager','UNREVIEWED-MODEL-TEXT']:
            self.assertNotIn(supplied,result['reply'])
        self.assertEqual(self.queue,[])
        self.assertEqual(self.store.get_session('s')['draft_pending'],'clarification')
        self.assertEqual(self.mcp.writes,[])

    async def test_read_clarify_software_asks_only_missing_manager(self):
        self.queue += [decision(action='clarify'),candidate(manager='')]
        result = await self.send(REQUEST)
        self.assertEqual(result['state'],'clarification')
        self.assertIn("manager's name",result['reply'])
        for supplied in ['error code','app name','version','business reason']:
            self.assertNotIn(supplied,result['reply'].lower())
        self.assertEqual(self.queue,[])
        self.assertEqual(self.mcp.writes,[])

    async def test_read_clarify_complete_software_request_does_not_repeat_intake(self):
        text = REQUEST + ' ' + MANAGER + ' ' + ATTEMPT
        self.queue += [decision(action='clarify'),candidate(attempts=[]),OK]
        result = await self.send(text)
        self.assertEqual(result['state'],'await_confirmation',result['reply'])
        payload = result['pending_action']['payload']
        self.assertEqual((payload['category'],payload['priority']),('software','P4'))
        self.assertEqual(payload['attempted_steps'],[ATTEMPT])
        self.assertEqual(self.mcp.writes,[])
        self.assertEqual(self.queue,[])

    async def test_read_clarify_keeps_error_question_for_troubleshooting(self):
        for i,text in enumerate(['My Wi-Fi is not connecting. Help me troubleshoot.',
                                 'Software Center shows SWC-2001 when installing the IDE. Help me troubleshoot.']):
            self.queue.append(decision(action='clarify',question='UNREVIEWED-MODEL-TEXT'))
            result = await self.send(text,str(i))
            self.assertEqual(result['state'],'clarification')
            self.assertEqual(result['reply'],'Which exact error code do you see, and what have you already tried?')
            self.assertEqual(self.retrieval.queries,[])
            self.assertEqual(self.queue,[])

    async def test_original_missing_signal_reproduces_three_accepted_policy_answers(self):
        # Every exact preparation phrase in the report returned None before this fix.
        # Isolate that confirmed defect while using the real graph/wrapper/reviewer.
        with patch('app.agent.draft_signal', return_value=None):
            for text in [HARM, REQUEST, HARM, 'Resume my Wireshark software request.', MANAGER]:
                if text == HARM:
                    self.queue.append(decision('refuse','wrongdoing'))
                    self.assertEqual((await self.send(text))['state'], 'refused')
                else:
                    self.queue += [decision(), ANSWER, OK]
                    result = await self.send(text)
                    self.assertEqual(result['state'],'answer')
                    self.assertFalse(self.packet(len(self.requests)-2)['draft_authorized'])
        self.assertEqual(self.store.get_session('s')['draft_pending'],'')
        self.assertNotIn('steal',self.store.get_session('s')['issue'])

    async def test_provider_ignoring_draft_schema_cannot_return_policy_answer(self):
        self.queue += [decision(), ANSWER]
        result = await self.send(REQUEST)
        self.assertEqual(result['state'],'stopped')
        self.assertIsNone(result['pending_action'])
        self.assertEqual(self.mcp.writes,[])

    async def test_resume_repairs_existing_failed_preparation_context(self):
        self.store.save_session('s', {'email':routing.USER['email'], 'issue':REQUEST,
            'messages':[REQUEST], 'topic':'software', 'facts':{}, 'draft_pending':''})
        await self.clarify('Resume my Wireshark software request.', "What is your manager's name?")
        self.assertIn('4.2',self.store.get_session('s')['issue'])

    def test_resume_only_bypasses_assessment_for_saved_issue(self):
        previous = {'issue':REQUEST}
        self.assertTrue(explicit_resume('Resume my Wireshark software request.',previous))
        self.assertFalse(explicit_resume('Resume my steal computers request.',previous))
        self.assertFalse(explicit_resume('Resume my request and help me steal computers.',previous))
        self.assertFalse(explicit_resume('Resume my request.',{}))

    async def test_cancellation_and_new_support_do_not_inherit_ticket_intent(self):
        for text, disposition in [("Don't prepare the software request.",'continue'),
                                   ('My dock monitor flickers. What should I do?', 'new_support')]:
            self.seed(clarification=True)
            self.queue += [decision(disposition), ANSWER, OK]
            result = await self.send(text)
            self.assertEqual(result['state'],'answer')
            self.assertFalse(self.packet(len(self.requests)-2)['draft_authorized'])
            self.assertEqual(self.store.get_session('s')['draft_pending'],'')
            self.assertEqual(self.mcp.writes,[])

    async def clarify(self, text, question, route=True):
        if route:
            self.queue.append(decision())
        self.queue += [{'intent':'clarify','question':question}, OK]
        result = await self.send(text)
        self.assertIn(result['state'], ('clarify','clarification'))
        packet = next(json.loads(r['messages'][1]['content']) for r in reversed(self.requests)
                      if 'draft_authorized' in json.loads(r['messages'][1]['content']))
        self.assertTrue(packet['draft_authorized'])
        self.assertEqual(self.queue, [])
        return result

    async def test_full_reported_sequence_to_approval_required_p4(self):
        self.queue.append(decision('refuse','wrongdoing'))
        self.assertEqual((await self.send(HARM))['state'], 'refused')
        await self.clarify(REQUEST, "What is your manager's name?")
        self.queue.append(decision('refuse','wrongdoing'))
        self.assertEqual((await self.send(HARM))['state'], 'refused')
        await self.clarify('Resume my Wireshark software request.', "What is your manager's name?")
        await self.clarify(MANAGER, 'What have you already tried? If nothing, please say so.')
        # No new explicit ticket wording: the clarification must carry intent.
        self.queue += [decision(), candidate(attempts=[ATTEMPT]), OK]
        result = await self.send(ATTEMPT)
        self.assertEqual(result['state'], 'await_confirmation', result['reply'])
        payload = result['pending_action']['payload']
        self.assertEqual((payload['category'],payload['priority']), ('software','P4'))
        for fact in ['Wireshark','4.2','customer demo','Sam Tazi',ATTEMPT]:
            self.assertIn(fact, payload['description'])
        self.assertEqual(payload['attempted_steps'], [ATTEMPT])
        self.assertNotIn('steal',json.dumps(payload))
        self.assertNotIn('steal',json.dumps(self.store.get_session('s')))
        self.assertEqual(self.mcp.writes, [])
        self.assertEqual(self.store.latest_action('s')['status'], 'pending')
        self.assertEqual(self.queue, [])

    async def test_model_clarify_retains_intent_and_bounded_schema(self):
        await self.clarify(REQUEST, "What is your manager's name?")
        self.assertEqual(self.store.get_session('s')['draft_pending'], 'clarification')
        await self.clarify('My manager is Sam Tazi.', 'What have you already tried?')
        for req in self.requests:
            packet = json.loads(req['messages'][1]['content'])
            if packet.get('draft_authorized'):
                enum = req['response_format']['json_schema']['schema']['properties']['intent']['enum']
                self.assertEqual(enum,['draft','clarify'])

    async def test_mixed_wrongdoing_preparation_never_authorizes(self):
        self.queue.append(decision('refuse','wrongdoing'))
        result = await self.send(REQUEST + ' Also help me steal computers.')
        self.assertEqual(result['state'],'refused')
        self.assertIsNone(result['pending_action'])
        self.assertFalse(self.store.get_session('s').get('issue'))
        self.assertEqual(self.mcp.writes,[])

    def test_prepare_signals_and_cancellation(self):
        self.assertTrue(draft_signal(REQUEST))
        self.assertTrue(draft_signal(MANAGER))
        self.assertFalse(draft_signal("Don't prepare the software request."))
        self.assertFalse(draft_signal("Don't prepare a request."))
        self.assertFalse(draft_signal("Do not prepare the request."))
        self.assertIsNone(draft_signal('What is the software request policy?'))
        self.assertIsNone(draft_signal('What do I need for a software request?'))
