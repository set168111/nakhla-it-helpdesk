"""Offline checks exercise evidence and policy boundaries, never pretend live RAG."""
import json
from pathlib import Path
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, patch

import numpy as np

from app.helpdesk_policy import matching_incident, resolve_precedence, contextual_chunks, ticket_policy, redact
from app.retrieval import BudgetLedger, BudgetExceeded, Retrieval, parse_documents


class RetrievalPolicyTests(unittest.IsolatedAsyncioTestCase):
    def test_all_documents_pdf_continuity_and_quarantine(self):
        docs,chunks,_=parse_documents()
        self.assertEqual(len(docs),20)
        pdfs=[c for c in chunks if c['id'] in ('KB-012','KB-013')]
        self.assertEqual(len(pdfs),2)
        self.assertTrue(all(c['pages'] and c['metadata']['version'] for c in pdfs))
        self.assertIn('PRN-07', next(c['text'] for c in pdfs if c['id']=='KB-013'))
        poisoned=next(c for c in chunks if c['id']=='KB-018')
        self.assertEqual(poisoned['text'],'Non-current source excluded from model evidence.')

    def test_conflict_points_removed_compatible_faq_retained(self):
        _,chunks,_=parse_documents()
        resolved=resolve_precedence(chunks,'Engineering')
        faq='\n'.join(c['text'] for c in resolved if c['id']=='KB-017')
        self.assertNotIn('one-time SMS',faq)
        self.assertNotIn('5 or more',faq)
        self.assertIn('24 hours',faq)
        self.assertFalse(any(c['id'] in ('KB-001','KB-005','KB-018') for c in resolved))
        self.assertTrue(any(c.get('policy_point')=='p1_threshold' and c['id']=='KB-015' for c in resolved))

    def test_department_priorities_and_refusal(self):
        finance=ticket_policy({'department':'Finance'},'VPN NX-403')
        self.assertEqual((finance['category'],finance['priority'],finance['immediate']),('security','P2',True))
        self.assertFalse(ticket_policy({'department':'Contractors'},'VPN access')['allowed'])
        self.assertTrue(ticket_policy({'department':'Contractors'},'VDI portal unavailable')['allowed'])
        self.assertEqual(ticket_policy({'department':'Engineering'},'VPN',affected_users=4)['priority'],'P1')
        self.assertEqual(ticket_policy({'department':'Executive Office'},'software request',blocked=False)['priority'],'P1')
        self.assertEqual(ticket_policy({'department':'Engineering'},'lost laptop')['priority'],'P1')
        self.assertEqual(ticket_policy({'department':'Engineering'},'software request')['priority'],'P4')

    def test_gateway_matching(self):
        status=json.loads(Path('services/data/status.json').read_text())
        self.assertEqual(matching_incident(status,{'vpn_gateway':'GW-2'},'NX-503')['id'],'INC-2207')
        self.assertIsNone(matching_incident(status,{'vpn_gateway':'GW-3'},'NX-503'))
        self.assertIsNone(matching_incident(status,{'vpn_gateway':'GW-2'},None))
        self.assertIsNone(matching_incident(status,{},'NXM-421'))

    async def test_offline_does_not_create_ready_vectors(self):
        with tempfile.TemporaryDirectory() as folder:
            retrieval=Retrieval(folder)
            result=await retrieval.ingest(offline=True)
            self.assertFalse(result['ready'])
            self.assertFalse((Path(folder)/'index.npz').exists())
            with self.assertRaisesRegex(RuntimeError,'Real embedding index'):
                await retrieval.search('NX-781')

    async def test_exact_error_closure_keeps_document_procedure_beyond_top_k(self):
        # Synthetic unit-test ranking only: no provider and no persisted vector
        # index. Deliberately use top1 so a header cannot crowd out later steps.
        with tempfile.TemporaryDirectory() as folder:
            retrieval=Retrieval(folder)
            retrieval.vectors=np.ones((len(retrieval.chunks),1),dtype=np.float32)
            expected={c['chunk_id'] for c in retrieval.chunks if c['id']=='KB-006'}
            with patch.object(retrieval,'embed',AsyncMock(return_value=np.ones((1,1),dtype=np.float32))):
                result=await retrieval.search('NID-423','Support',limit=1)
                self.assertTrue(expected.issubset({c['chunk_id'] for c in result}))
                self.assertIn('/unlock','\n'.join(c['text'] for c in result if c['id']=='KB-006'))
                self.assertTrue(all(c['metadata']['status']=='current' for c in result))
                audit=retrieval.last_audit
                self.assertTrue(any(c['id']=='KB-006' and c['reason']=='exact_error_document_closure' for c in audit['selected']))
                self.assertTrue(any(c['id']=='KB-018' and c['reason']=='non_current_quarantined' for c in audit['excluded']))
                self.assertEqual({c['chunk_id'] for c in audit['selected']},{c['chunk_id'] for c in result})

    async def test_unknown_error_does_not_gain_adjacent_document_closure(self):
        with tempfile.TemporaryDirectory() as folder:
            retrieval=Retrieval(folder)
            retrieval.vectors=np.ones((len(retrieval.chunks),1),dtype=np.float32)
            with patch.object(retrieval,'embed',AsyncMock(return_value=np.ones((1,1),dtype=np.float32))):
                result=await retrieval.search('CRM-1150','Sales',limit=1)
            self.assertTrue(all(c['id'] in {'SP-001','SP-002','KB-015','KB-016'} for c in result))
            self.assertTrue(all(c['unknown_error_codes']==['CRM-1150'] for c in result))

    async def test_finance_vpn_retrieval_excludes_generic_client_fixes(self):
        with tempfile.TemporaryDirectory() as folder:
            retrieval=Retrieval(folder)
            retrieval.vectors=np.ones((len(retrieval.chunks),1),dtype=np.float32)
            with patch.object(retrieval,'embed',AsyncMock(return_value=np.ones((1,1),dtype=np.float32))):
                finance=await retrieval.search('NakhlaConnect NX-403 from home','Finance',limit=1)
                finance_no_code=await retrieval.search('My VPN is broken','Finance',limit=1)
                engineering=await retrieval.search('NakhlaConnect NX-403 from home','Engineering',limit=1)
            self.assertTrue(all(c['id'] in {'SP-001','SP-002','KB-015','KB-016','KB-002'} for c in finance))
            vpn=[c for c in finance if c['id']=='KB-002']
            self.assertEqual(len(vpn),1)
            self.assertEqual(vpn[0]['section'],'Exceptions / Finance')
            self.assertIn('straight to Security Operations',vpn[0]['text'])
            self.assertIn('Do not walk Finance staff',vpn[0]['text'])
            self.assertNotIn('Approve the NakhlaKey prompt within 60 seconds','\n'.join(c['text'] for c in finance))
            self.assertNotIn('Check your version','\n'.join(c['text'] for c in finance))
            self.assertIn('Approve the NakhlaKey prompt within 60 seconds','\n'.join(c['text'] for c in engineering))
            self.assertTrue(any(c['id']=='KB-002' and c['section']=='Exceptions / Finance' for c in finance_no_code))

    async def test_audit_records_department_scope_and_clears_on_failed_search(self):
        with tempfile.TemporaryDirectory() as folder:
            retrieval=Retrieval(folder)
            retrieval.vectors=np.ones((len(retrieval.chunks),1),dtype=np.float32)
            with patch.object(retrieval,'embed',AsyncMock(return_value=np.ones((1,1),dtype=np.float32))):
                await retrieval.search('Finance VPN NX-403','Finance',limit=1)
            self.assertTrue(any(c['id']=='KB-002' and c['reason']=='department_policy_excerpt' for c in retrieval.last_audit['selected']))
            self.assertTrue(any(c['id']=='KB-002' and c['reason']=='department_policy_scope_excluded' for c in retrieval.last_audit['excluded']))
            self.assertNotIn('text',str(retrieval.last_audit))
            with patch.object(retrieval,'embed',AsyncMock(side_effect=RuntimeError('offline injected failure'))):
                with self.assertRaises(RuntimeError):
                    await retrieval.search('NX-403','Finance')
            self.assertEqual(retrieval.last_audit,{})

    def test_finance_context_filter_does_not_rewrite_non_vpn_evidence(self):
        _,chunks,_=parse_documents()
        selected=resolve_precedence(chunks,'Finance')
        self.assertIs(contextual_chunks(selected,'Finance','NID-423 account lockout'),selected)

    def test_budget_reservation_survives_new_instance(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger=BudgetLedger(folder,ceiling=.01)
            reservation=ledger.reserve(.007,'test')
            with self.assertRaises(BudgetExceeded):
                BudgetLedger(folder,ceiling=.01).reserve(.004,'other')
            ledger.settle(reservation,.002)
            self.assertAlmostEqual(ledger.snapshot()['remaining_usd'],.008)
            self.assertEqual(BudgetLedger(folder,ceiling=.01).snapshot()['calls'],1)

    def test_redaction(self):
        self.assertNotIn('secret123',redact('password=secret123'))
        self.assertNotIn('7731',redact('7731'))
        self.assertNotIn('hunter2',redact('My password is hunter2.'))
        self.assertNotIn('123456',redact('OTP 123456'))
        self.assertNotIn('ABCD-EFGH',redact('backup code: ABCD-EFGH'))
        self.assertNotIn('private-token',redact('Authorization: Bearer private-token'))
        self.assertEqual(redact('NX-781 version 5.4.2'),'NX-781 version 5.4.2')

    def test_procedural_credential_descriptions_are_not_secret_assignments(self):
        sentences = [
            "The one-time activation link for the new starter's first password is sent to the hiring manager's email address.",
            "Backup codes are generated at enrolment and must be kept offline; each code can be used once.",
            "If no NakhlaKey device and no backup codes are available, assisted reset requires manager approval and identity verification.",
        ]
        for sentence in sentences:
            self.assertEqual(redact(sentence),sentence)
        for secret in ['password is hunter2','backup code is AB12CD','OTP is 123456','api key is private-secret-token']:
            self.assertIn('[REDACTED]',redact(secret))

    def test_procedural_clause_cannot_swallow_a_later_secret_assignment(self):
        adversarial = [
            'Backup codes are available, password is hunter2',
            'Backup codes are available, password=hunter2',
            'Backup code: AB12CD, password is hunter2',
        ]
        for sentence in adversarial:
            self.assertNotIn('hunter2',redact(sentence))
        self.assertEqual(redact('My password is available'),'My password is [REDACTED]')
        self.assertNotIn('AB12CD',redact('Our backup codes are AB12CD, EF34GH'))

    def test_concurrent_budget_and_invalid_values(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger=BudgetLedger(folder,ceiling=.01)
            def reserve(_):
                try:
                    return ledger.reserve(.006,'parallel')
                except BudgetExceeded:
                    return None
            with ThreadPoolExecutor(max_workers=2) as executor:
                results=list(executor.map(reserve,range(2)))
            self.assertEqual(sum(bool(r) for r in results),1)
            for invalid in [float('nan'),float('inf'),-.01,0]:
                with self.assertRaises(ValueError):
                    ledger.reserve(invalid,'invalid')


if __name__=='__main__':
    unittest.main()
