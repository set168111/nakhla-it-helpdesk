import unittest
from app.agent import allowed_read_actions

class ReadIntentTests(unittest.TestCase):
    def test_new_draft_with_known_error_requires_policy_read(self):
        self.assertEqual(allowed_read_actions('Software Center fails with SWC-2001. Please open a ticket.', {'error_code':'SWC-2001'}), ['retrieve'])
    def test_explicit_history_and_owned_id_remain_available(self):
        self.assertIn('history', allowed_read_actions('Show my ticket history.', {'error_code':'NX-503'}))
        self.assertIn('get_ticket', allowed_read_actions('Show ticket IT-1001.', {}))
    def test_history_is_not_selected_from_unrequested_context(self):
        self.assertNotIn('history', allowed_read_actions('My installation fails.', {}))
