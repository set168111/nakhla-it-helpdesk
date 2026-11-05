"""Offline display tests; real HTTP admin wiring, fake simulator, temporary auth stores."""
import copy
from html.parser import HTMLParser
import math
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('GRADIO_ANALYTICS_ENABLED', 'False')
from ui.app_ui import usage_markdown, side_panels, reset_panels, MENU
from tests import test_demo_admin as admin_tests
from tests.test_demo_admin import DemoAdminBase
from tests.ui_fixtures import USAGE, TICKETS, ORDER, HEADERS


class Table(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.rows, self.cells, self.cell = [], [], None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.cells = []
        if tag in {'td', 'th'}:
            self.cell = ''

    def handle_data(self, value):
        if self.cell is not None:
            self.cell += value

    def handle_endtag(self, tag):
        if tag in {'td', 'th'}:
            self.cells.append(self.cell)
            self.cell = None
        if tag == 'tr':
            self.rows.append(self.cells)


class UsageRenderingTests(unittest.TestCase):
    def test_confirmed_and_estimated_portions_use_existing_contract(self):
        confirmed = usage_markdown(USAGE['confirmed'])
        self.assertIn('Input tokens: 120', confirmed)
        self.assertIn('Output tokens: 30', confirmed)
        self.assertIn('Confirmed cost (USD): 0.00300000', confirmed)
        mixed = usage_markdown(USAGE['estimated'])
        self.assertIn('Cost (USD): 0.00500000', mixed)
        self.assertIn('Confirmed cost (USD): 0.00300000', mixed)
        self.assertIn('Estimated cost (USD): 0.00200000', mixed)

    def test_missing_invalid_and_partial_values_are_unknown_not_zero(self):
        for value in [None, {}, [], {'prompt_tokens': None, 'completion_tokens': '5', 'cost_usd': math.nan},
                      {'prompt_tokens': -1, 'completion_tokens': False, 'cost_usd': math.inf}]:
            with self.subTest(value=value):
                rendered = usage_markdown(value)
                self.assertIn('Input tokens: Unknown', rendered)
                self.assertIn('Output tokens: Unknown', rendered)
                self.assertIn('Cost (USD): Unknown', rendered)
                self.assertNotIn('0.00000000', rendered)
        unknown = usage_markdown(USAGE['unknown'])
        self.assertIn('final billing incomplete', unknown)
        self.assertIn('Output tokens: Unknown', unknown)
        self.assertIn('0.02000000 (not a confirmed charge)', unknown)
        self.assertIn('may be partial', unknown)

    def test_reported_zero_is_distinct_from_missing_and_basis_is_honest(self):
        rendered = usage_markdown({'prompt_tokens': 0, 'completion_tokens': 0, 'cost_usd': 0,
                                   'confirmed_cost_usd': 0})
        self.assertIn('Input tokens: 0', rendered)
        self.assertIn('Cost (USD): 0.00000000', rendered)
        self.assertIn('confirmation basis unavailable', rendered)
        self.assertNotIn('Confirmed cost', rendered)

    def test_usage_stays_below_tools_and_missing_turn_clears_previous_usage(self):
        data = {'usage': USAGE['confirmed']}
        before = copy.deepcopy(data)
        tools = side_panels(data)[1]
        self.assertLess(tools.index('Tool calls'), tools.index('Last-turn usage'))
        self.assertEqual(data, before)
        self.assertNotIn('0.003', side_panels({})[1])
        self.assertIn('Cost (USD): Unknown', reset_panels()[6])
        self.assertEqual([label for label, _ in MENU],
                         ['Demo video', 'Presentation', 'Admin tickets', 'App health', 'Demo accounts'])


class AdminTableTests(DemoAdminBase):
    def setUp(self):
        super().setUp()
        admin_tests.DummySimulator.hits.clear()
        self.addCleanup(admin_tests.DummySimulator.hits.clear)

    def test_authenticated_table_order_headers_and_no_false_ticket_attribution(self):
        self.admin_login()
        with patch.object(admin_tests, 'TICKETS', {'tickets': TICKETS, 'count': len(TICKETS)}):
            response = self.client.get('/demo/tickets')
        self.assertEqual(response.status_code, 200)
        rows = Table(response.text).rows
        self.assertEqual(rows[0], HEADERS)
        self.assertEqual([row[0] for row in rows[1:]], ORDER)
        self.assertTrue(all(len(row) == 9 and row[-2] == 'Created' and row[-1] == 'Unavailable' for row in rows[1:]))
        self.assertNotIn('<script>window.ticketXss', response.text)

    def test_every_ticket_column_is_escaped(self):
        self.admin_login()
        attack = '<img src=x onerror="alert(1)"> & text'
        ticket = {key: attack for key in ['ticket_id', 'created_at', 'subject', 'category', 'priority', 'status', 'requester_email']}
        with patch.object(admin_tests, 'TICKETS', {'tickets': [ticket], 'count': 1}):
            response = self.client.get('/demo/tickets')
        self.assertNotIn('<img', response.text)
        self.assertEqual(Table(response.text).rows[1], [attack] * 7 + ['Created', 'Unavailable'])

    def test_historical_ticket_never_uses_unattributed_or_approval_cost(self):
        self.admin_login()
        historical = {**TICKETS[0], 'ticket_id': 'IT-1021', 'cost_usd': 0,
                      'usage': USAGE['estimated'], 'latest_chat_cost': 123}
        with patch.object(admin_tests, 'TICKETS', {'tickets': [historical], 'count': 1}):
            response = self.client.get('/demo/tickets')
        self.assertEqual(Table(response.text).rows[1][-1], 'Unavailable')
