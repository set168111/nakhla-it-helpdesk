# Conversation recall and draft-intent fix - 30 October 2026

Three kinds of evidence are kept apart here. None of them changes the historical 65/69 score (repeats 22/23, 22/23, 21/23; three unresolved S2-07 attempts and one OWN-08 `APIConnectionError`), which is preserved unchanged in `evidence/supplemental-dock-2026-10-26/`.

## 1. The failure (read-only diagnosis of a user-observed chat)

In an existing chat the requester reported VPN error NX-999 with "I have not tried anything yet ... Please prepare a ticket", and ticket IT-2001 was created through the normal approval path. A later question asked which error they had reported and what they had tried. The assistant re-asked "What have you already tried?" instead of answering. The stored session still held the error code and the statement, and the model was given both, so this was not memory loss.

Two defects in `app/agent.py`:

- **Sticky draft intent.** Draft authorisation was derived from the whole accumulated issue text, so an old "please prepare a ticket" kept restricting the model to draft-or-clarify on a question that was neither.
- **No route for conversation recall.** A question about the chat was handled as a troubleshooting turn. It could be misread as a report of attempts, and the only available answers came from the KB or the ticket system.

## 2. The change (source: `app/agent.py`; tests: `tests/test_agent_workflow.py`)

- A ticket draft is allowed only when the current message asks for one, answers a clarification asked while preparing a requested ticket, or gives an impact update right after a drafted ticket. An old request alone authorises nothing.
- Questions are no longer recorded as attempted steps.
- A question about what this requester reported or tried earlier is recognised by several patterns, not one phrase, and is answered from the saved session. There is no model call, no MCP read or write, no KB citation, and no draft. The reply says it comes from the conversation, not the knowledge base. Genuine attempts are quoted with their source; if nothing was reported, it says so.
- Recall wording that also contains a real request (how to fix, a ticket, a new error code, a new issue) is not treated as recall.
- Approval controls, policy enforcement, identity checks, source attribution and bounded execution are unchanged. S2-07 behaviour is unchanged.

## 3. Offline mocked tests - automated, no live or model calls

- 11 new regression tests in `tests/test_agent_workflow.py`; that module ran 69 tests, OK.
- The six relevant modules (workflow, approvals, read intent, retrieval policy, contract safety, eval measurement) ran **117 tests, OK, 2 live opt-ins skipped**.
- These are offline mocked unit results. They are not a new evaluation, not a live run, and not part of 65/69.

## 4. User-reported manual evidence - not an automated replay

After rebuilding only the app container (agent.py runtime hash `1a1f55cd2435e0c2`, matching the fixed source), the user reports that the existing chat recalled NX-999 and "I have not tried anything yet", with state `recall`, no draft and no tools. This is a **manual user report**. It was not replayed automatically, and no ticket state was re-queried. It is separate from the mocked tests above and from the historical score.

## Limitations

- The manual retest is a single user-reported observation of one conversation.
- Recall detection is pattern-based and conservative. Unusual phrasings may fall through to the normal flow, which stays grounded and approval-gated.
- Recall answers use only the last six stored messages.
- Not re-run live: the full 23-case acceptance suite. S2-07 stays unresolved (KB-015 P2/P3 rules versus the sample's P3 expectation).
