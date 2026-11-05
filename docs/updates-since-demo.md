# Updates since the live demo

The video and presentation show an earlier version. Since the live demo, the following improvements have been added.

- Individual employee login and separate protected demo-admin access.
- Ownership checks for conversations, ticket reads and approvals.
- Improved clarification, conversation recall and request resumption.
- Better handling of unrelated or harmful requests, with remaining snippet limitations noted below.
- Clearer lockout-policy conditions, including the daily count and unknown-cause requirements.
- Last-turn token and cost display, including honest unknown and estimated values.
- One combined historical/new ticket table, grouped by status and sorted newest first within each group.
- Saved grading history is retained until explicit cleanup.

Current limitations:

- Per-ticket cost attribution remains unavailable.
- Snippet clarification remains safe but sometimes unhelpful.
- Historical evaluation remains 65/69; later checks are separate evidence.

Later automated and manual checks cover their recorded scope. No comprehensive
security certification or new full-suite acceptance is claimed.

The same public information is served at `/demo/updates` through a fixed route;
no documentation directory or private file tree is exposed.
