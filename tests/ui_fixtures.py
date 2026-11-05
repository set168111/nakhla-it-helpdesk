"""Synthetic UI fixtures only; no live tickets, credentials or provider calls."""
USAGE = {
    'confirmed': {'prompt_tokens': 120, 'completion_tokens': 30, 'cost_usd': .003,
                  'confirmed_cost_usd': .003, 'calculated_cost_usd': 0, 'unknown_reserved_usd': 0},
    'estimated': {'prompt_tokens': 180, 'completion_tokens': 45, 'cost_usd': .005,
                  'confirmed_cost_usd': .005, 'calculated_cost_usd': .002, 'unknown_reserved_usd': 0},
    'unknown': {'prompt_tokens': 20, 'completion_tokens': None, 'cost_usd': None,
                'confirmed_cost_usd': .001, 'calculated_cost_usd': 0, 'unknown_reserved_usd': .02},
    'missing': None,
}

TICKETS = [
    {'ticket_id': 'IT-2001', 'status': 'open', 'created_at': '2026-11-04T10:00:00Z',
     'subject': 'Isolated browser test ticket'},
    {'ticket_id': 'IT-2002', 'status': 'closed', 'created_at': '2026-11-04T11:00:00Z'},
    {'ticket_id': 'IT-2003', 'status': 'Open', 'created_at': '2026-11-04T12:00:00Z',
     'subject': '<script>window.ticketXss=1</script>'},
    {'ticket_id': 'IT-2004', 'status': 'resolved', 'created_at': '2026-11-04T13:00:00Z'},
    {'ticket_id': 'IT-2005', 'status': 'pending', 'created_at': '2026-11-04T20:00:00Z'},
    {'ticket_id': 'IT-2006', 'status': 'OPEN', 'created_at': 'invalid date'},
    {'ticket_id': 'IT-2007', 'status': 'open', 'created_at': '2026-11-04T13:30:00+03:00'},
]
for ticket in TICKETS:
    ticket.update({'requester_email': 'tester.two@nakhla.example', 'category': 'software', 'priority': 'P4'})
    ticket.setdefault('subject', 'Synthetic ticket')
    # Deliberately untrusted: renderer must not mistake simulator fields for preparation attribution.
    ticket['cost_usd'] = 999
    ticket['usage'] = USAGE['confirmed']

ORDER = ['IT-2003', 'IT-2007', 'IT-2001', 'IT-2006', 'IT-2004', 'IT-2002', 'IT-2005']
HEADERS = ['Ticket ID', 'Created', 'Subject', 'Category', 'Priority', 'Status', 'Requester',
           'Origin', 'AI cost to create ticket (USD)']
