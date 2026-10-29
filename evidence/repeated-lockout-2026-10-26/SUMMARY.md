# Repeated-lockout routing fix - 26 October 2026

## Docker/live follow-up - verified26October2026

Only app rebuilt/restarted with --no-deps; data bind mount/index/SQLite/ledger preserved, simulator/UI untouched and not reset. All43 source/config files checked (including requirements.txt) match host current source. App/simulator/UI healthHTTP200; container stdio MCP listed six tools and directory/status reads passed. See docker-live-verification.json and docker-live-build-start.log. Source unchanged during live check (live-source-before/after.json).

Exactly ONE live /api/chat request as sara.mikhail@nakhla.example: "My NakhlaID account shows NID-423 and has locked three times today without a known cause. I already checked saved passwords on my devices and found none. Please prepare a ticket." PASS in8.797s: security/P2 draft awaiting approval; SP-001 and KB-006 citations; no impact/workaround clarification; truthful attempts/requester retained. No approval or create_ticket sent; stored action still pending and simulator ticket collection unchanged. Real Reviewer accepted the response. API-to-MCP targeted evidence, not a queued-browser/manual pass. Raw evidence: live-result.json, live-checks.json, live-traces.json.

Ledger before paid request: available$0.56644988. Confirmed cost$0.00583914, new unknown$0.00000000. Actual project totals: confirmed$1.89905922, retained unknown$0.04033004, available**$0.56061074**. No source changes, full-suite rerun, Git or release actions. All historical scores remain separate.

UI http://127.0.0.1:7860. Manual test: New chat as sara.mikhail@nakhla.example; submit the exact message above. Expect an approval-required security/P2 draft, SP-001/KB-006 Sources, truthful attempts and no impact/workaround question. STOP before approval. The user has now explicitly reported the scoped manual check PASS; see follow-up below.

## Earlier offline phase - superseded Docker/live pending status


Confirmed against unchanged KB-006 Escalation and SP-001 section3: three or more unexplained lockouts in one day require Security Operations, category security, priorityP2. The old deterministic path returned identity_access/None and asked for impact/workaround. Two focused offline regressions failed before the fix (before.log), then passed after it (focused-after.log).

Minimal changes: app/helpdesk_policy.py recognizes explicit count>=3, today/in one day, and unknown-cause wording, assigning security/P2 after existingP1 precedence. It does not mark a possible guessing attack as an activeP1 incident. app/agent.py preserves this documented priority rather than requesting unrelated impact facts. No automatic draft/approval, invented troubleshooting or Finance immediate-escalation semantics were added. Existing requester attempts and fresh approval flow remain required. The lexical recognizer is bounded, not an exhaustive natural-language event/cause parser.

Focused coverage: normal and numeric/unexplained reports; missing count/day/cause and known-old-password negatives; usable-workaround stillP2; VIP/four-users/actual compromise stillP1. Same-session NID-423 follow-up retains requester, department, error and truthful steps, creates no write before approval, rejects safely, gives a fresh actionID, rejects stale approval and writes once under double approval. Model/Reviewer responses and MCP are scripted offline doubles, not live quality evidence.

Relevant offline suite:97 tests,95passed,2live opt-ins skipped; actual unittest exit0 (relevant-offline.log). Existing Finance/Contractor/VIP, CRM impact and approval tests are included. No full suite, paid calls, provider requests, real ticket writes or services restarted. Source files changed: app/helpdesk_policy.py, app/agent.py and custom tests/test_agent_workflow.py. Supplied cases/tests/runner/data/services/pins unchanged.

Docker: previous verified image/42-file source match PREDATES this fix. The existing running app was left untouched and does not include the new lockout rule. Needed next targeted verification, only if authorized: rebuild/restart the affected local app, compare source hashes/health/MCP, then one live repeated-lockout follow-up to verify real retrieval/Reviewer accepts security/P2 without impact clarification and still waits for approval. No full repeated acceptance is justified solely by this bounded fix; budget approval is required before a live model call.

Historical65/69 remains untouched: repeat22/23,22/23,21/23; S2-07 failed3/3 and OWN-08 had one APIConnectionError. Its later passing retest remains separate. Supplemental503 initial1/1+repeated3/3 remains separate from supplied S2-07. Seven manual passes remain user-reported, not new automated evidence. Solo contributions/AI assistance remain recorded; no peer/trainer approval implied.

S2-07 note now explicitly acknowledges the official dataset/student_scenarios/sample_requests.md expectation hardware/P3 alongside the missing KB-015 impact/workaround facts; the priority safeguard and supplied case remain unchanged. Instructor clarification unavailable; this remains a disclosure, not the next required human action.

No Git, publishing, release, submission or video actions. Actual ledger and source hashes in checkpoint.json. Current-record reconciliation keeps earlier milestone statements in clearly labelled historical sections rather than treating passed manual/README work as outstanding.


User-reported manual follow-up26October2026: PASS - security/P2, SP-001 and KB-006 Sources, exact reported attempted step ("I already checked saved passwords on my devices and found none."), no unnecessary clarification and awaiting approval. This is separate from the automated live API result. No approval, creation, repeat test or paid call is claimed for recording this report.
