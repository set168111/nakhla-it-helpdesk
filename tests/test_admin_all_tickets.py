"""Offline combined admin-ticket view and original simulator contract checks."""
import copy
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from tests.test_demo_admin import DemoAdminBase, DummySimulator
from tests.test_ui_enhancements import Table


def ticket(identifier, status='open', created='2026-11-04T10:00:00Z', subject='Synthetic'):
    return {'ticket_id': identifier, 'status': status, 'created_at': created, 'subject': subject,
            'category': 'software', 'priority': 'P4', 'requester_email': 'fake@nakhla.example'}


def listing(*tickets):
    return {'tickets': list(tickets), 'count': len(tickets)}


class CombinedTicketTests(DemoAdminBase):
    def setUp(self):
        super().setUp()
        DummySimulator.hits.clear()
        self.addCleanup(DummySimulator.hits.clear)
        self.admin_login()

    def render(self, all_records, created_records):
        requests = []
        original_client = httpx.AsyncClient

        def respond(request):
            requests.append((request.method, request.url.path, request.url.query))
            value = all_records if request.url.query == b'all=true' else created_records
            if isinstance(value, Exception):
                raise value
            if isinstance(value, httpx.Response):
                return value
            return httpx.Response(200, json=value)

        def client(**kwargs):
            return original_client(transport=httpx.MockTransport(respond), **kwargs)

        with patch('app.demo_admin.httpx.AsyncClient', side_effect=client):
            response = self.client.get('/demo/tickets')
        self.assertEqual(requests, [('GET', '/admin/tickets', b'all=true'), ('GET', '/admin/tickets', b'')])
        return response, Table(response.text).rows

    def test_archive_only(self):
        response, rows = self.render(listing(ticket('IT-1021', 'closed')), listing())
        self.assertEqual(response.status_code, 200)
        self.assertIn('Total: 1 | Historical: 1 | Created: 0', response.text)
        self.assertEqual(rows[1][-2:], ['Historical', 'Unavailable'])
        self.assertNotIn('Incomplete view', response.text)

    def test_created_only(self):
        new = ticket('IT-2001')
        response, rows = self.render(listing(new), listing(new))
        self.assertIn('Total: 1 | Historical: 0 | Created: 1', response.text)
        self.assertEqual(rows[1][-2:], ['Created', 'Unavailable'])

    def test_combined_status_groups_and_timezone_order(self):
        historical = [ticket('IT-1001', 'closed', '2026-11-04T12:00:00Z'),
                      ticket('IT-1002', 'open', '2026-11-04T13:00:00+03:00'),
                      ticket('IT-1003', 'resolved', '2026-11-04T13:00:00Z')]
        created = [ticket('IT-2001', 'open', '2026-11-04T11:00:00Z'),
                   ticket('IT-2002', 'pending', '2026-11-04T20:00:00Z')]
        response, rows = self.render(listing(*(historical + created)), listing(*created))
        self.assertIn('Total: 5 | Historical: 3 | Created: 2', response.text)
        self.assertEqual([r[0] for r in rows[1:]], ['IT-2001', 'IT-1002', 'IT-1003', 'IT-1001', 'IT-2002'])
        self.assertEqual([r[-2] for r in rows[1:]], ['Created', 'Historical', 'Historical', 'Historical', 'Created'])
        self.assertTrue(all(r[-1] == 'Unavailable' for r in rows[1:]))

    def test_duplicates_have_one_row_created_wins_and_newest_within_source(self):
        old = ticket('IT-1001', 'closed', subject='archive version')
        older = ticket('IT-1001', created='2026-11-03T10:00:00Z', subject='older created')
        newer = ticket('IT-1001', created='2026-11-04T10:00:00Z', subject='newest created')
        data = listing(old, copy.deepcopy(old), older, newer)
        before = copy.deepcopy(data)
        response, rows = self.render(data, listing(older, newer, copy.deepcopy(newer)))
        self.assertEqual(data, before)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][2], 'newest created')
        self.assertEqual(rows[1][-2:], ['Created', 'Unavailable'])
        self.assertIn('Total: 1 | Historical: 0 | Created: 1', response.text)

    def test_unavailable_all_source_keeps_created_without_fake_historical_zero(self):
        response, rows = self.render(httpx.Response(503), listing(ticket('IT-2001')))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Incomplete view', response.text)
        self.assertIn('Total: Unavailable | Historical: Unavailable | Created: 1', response.text)
        self.assertEqual(rows[1][-2], 'Created')

    def test_unavailable_created_source_keeps_all_but_origin_is_unknown(self):
        response, rows = self.render(listing(ticket('IT-1001')), httpx.ReadTimeout('synthetic timeout'))
        self.assertIn('Incomplete view', response.text)
        self.assertIn('Total: 1 | Historical: Unavailable | Created: Unavailable', response.text)
        self.assertEqual(rows[1][-2], 'Unavailable')

    def test_both_unavailable_never_claim_zero_total(self):
        response, rows = self.render(httpx.Response(500), httpx.Response(503))
        self.assertEqual(response.status_code, 502)
        self.assertEqual(len(rows), 1)
        self.assertIn('Total: Unavailable | Historical: Unavailable | Created: Unavailable', response.text)
        self.assertNotIn('Total: 0', response.text)

    def test_invalid_sources_are_not_silently_empty(self):
        for bad in [None, [], {}, {'tickets': [], 'count': 1}, {'tickets': [{}], 'count': 1},
                    {'tickets': [], 'count': False}]:
            with self.subTest(bad=bad):
                response, _ = self.render(bad, listing())
                self.assertIn('Incomplete view', response.text)
                self.assertIn('Historical: Unavailable', response.text)

    def test_complete_empty_is_a_real_zero(self):
        response, rows = self.render(listing(), listing())
        self.assertIn('Total: 0 | Historical: 0 | Created: 0', response.text)
        self.assertEqual(len(rows), 1)
        self.assertNotIn('Incomplete view', response.text)

    def test_historical_text_is_escaped_and_protection_is_unchanged(self):
        attack = '<script>window.attack=1</script>'
        response, rows = self.render(listing(ticket('IT-1001', subject=attack)), listing())
        self.assertNotIn(attack, response.text)
        self.assertEqual(rows[1][2], attack)
        self.assertEqual(rows[1][-2], 'Historical')
        self.client.post('/demo/logout')
        with patch('app.demo_admin.httpx.AsyncClient', side_effect=AssertionError('must not read sources')):
            self.assertEqual(self.client.get('/demo/tickets').status_code, 303)


class SimulatorContractTests(DemoAdminBase):
    def test_supported_default_and_all_flag_contracts_unchanged(self):
        # In-process simulator only, synthetic state: no service, file write, reset or creation.
        from services import helpdesk_api as simulator
        historical, created = ticket('IT-1001'), ticket('IT-2001')
        with patch.dict(simulator.STATE, {'archive': [historical], 'created': [created]}):
            client = TestClient(simulator.app)
            self.assertEqual(client.get('/admin/tickets').json(), listing(created))
            self.assertEqual(client.get('/admin/tickets?all=true').json(), listing(historical, created))
