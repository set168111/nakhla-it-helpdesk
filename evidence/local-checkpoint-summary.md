# Local user-testing checkpoint - 24 October 2026

Local testing only. Instructor review is not completed, approved or waived. No release/submission approval.

Final fixed-source repeated suite: **68/69 (98.55%)**. All 23 cases ran three times; no failures removed. Source matches the recorded start manifest: **True**. Ten supplied cases/runner/assertions remain unchanged; thirteen original cases add PDF, security, memory, failure and approval state assertions.

| Repeat | Passed |
|---|---|
| 1 | 22/23 |
| 2 | 23/23 |
| 3 | 23/23 |

Whole-case wall time: mean **13.10s**, nearest-rank p95 **27.30s**. Turn wall time: mean **7.51s**, nearest-rank p95 **19.86s**. Whole-case time includes setup, all turns and assertions; turn p95 is not case p95. Small local samples are descriptive, not an SLA.

Exact suite cost/average is **unknown** because one turn has unknown billing (0 missing usage). Confirmed partial cost **$0.23335552**, unresolved reservations **$0.01635216**. Confirmed cost per attempted case **$0.00338196** is a lower bound; adding retained reservations gives a conservative accounting amount **$0.00361895/case**, not settled provider billing.

Project ledger at checkpoint: confirmed spent **$1.25753290**, outstanding reservations **$0.02552396**, remaining spendable headroom **$1.21694314** of the **$2.50** ceiling. Includes earlier ingestion/evaluations and subsequent smoke checks. Reservations are retained for uncertain calls. One-time embedding builds were $0.00022396 and $0.00022386; no paid judge was used.

## Actual final failures

- Repeat 1, **S2-08**: required KB-002 citation missing after provider timeout (empty citations). Reply: I could not verify this response because a dependency, safety, budget or time check failed. No ticket was confirmed. Please try again or contact the IT Service Desk.

## Failure/fix evidence and review

Previous candidate: **65/69**, case p95 21.80s, mean cost $0.00378528/case; raw `local-user-testing/`. S2-06 returned own history instead of a requested new draft in all three repeats. Corrected native read selection permits history/get-ticket only for explicit current requests and excludes premature clarification for a known error. Three focused offline tests cover the boundary. The previous OWN-06 failure was a false Reviewer P4 interpretation; code preserved VIP P1 and wrote nothing. This remains a model-reliability concern even if subsequent cases pass.
Independent read-only review is in `local-user-testing-review.md` and `local-checkpoint-review-addendum.md`. The v2 S2-08 timeout trace is `aba3540433de47f3b7490862889da28c`; it stopped safely rather than outputting unsafe content, but still fails acceptance. No expensive generation retry was added to hide it.
Earlier actual baseline failures and fixes remain in versioned evidence folders (first supplied 4/10, later 10/10 baseline; original and repeated failures preserved). `failure-before-after.json` specifically records an injected transient503 and same-key recovery, not an invented application defect.

## Other checks and gaps

- Offline87 tests:85 passed,2 live opt-ins skipped; `local-checkpoint-offline-v2.log`. Setup historical validator1301 checks and kit six-tool MCP checks passed. Offline doubles are not live AI evidence.
- Fresh ready-start/UI persistence outcome: `local-checkpoint-persistence.json`; process identity/health: `local-checkpoint-processes.json`. Inspect actual outcomes rather than assuming a file implies success.
- Existing Docker Compose config and image inspection passed, but images predate latest source. Current-source packaged fresh/cached startup and regression remain unverified; rebuild/release deferred until after user testing.
- Reviewer/provider failures can make valid requests stop. Failure-path trace top-level model_calls may underreport graph-local calls; use per-event call records/shared billing ledger for accounting, not that summary counter.
- Asserted employee identity is not production authentication; simulator tickets reset on restart, while application sessions/actions/index/budget persist. Real-company integration, scale and arbitrary-query quality are unverified.
- Human local acceptance, instructor review, team/registration/check-ins, final recording/presentation and eventual release/submission remain pending. No executable, publish/deploy/push/tag/video work was performed.
- Later capstone optimisation remains planned: use these baseline metrics to justify one small measured change; compare quality/cost/latency before adoption. No caching optimisation is claimed implemented.

Artifacts: `local-user-testing-v2/scorecard.md`, `.json`, `.case-metrics.json`, `source-at-start.json`, `source-at-end.json`; all prior failures retained.

Current-source integrity:37 supplied files compare unchanged to the source kit with CRLF-only text normalization; see supplied-integrity-current.json. Fresh queued UI/process restart follow-up succeeded; app/simulator health and UI each HTTP200. Initial probe passed a hidden Gradio state as a public argument, causing422 without a model call; corrected harness/evidence retained separately in local-checkpoint-persistence-harness-error.json.

Optional supplied --judge criteria were skipped, not passed; the wrapper refuses unmetered judge calls. Independent manual reviews have their own bounded scope and do not constitute an automated judge score.

## Independent final semantic findings - unresolved

The read-only final reply audit found defects beyond the shared runner assertions:

- **S2-03 repeat3:** the reply first correctly states minimum client5.4, then incorrectly calls5.4.2 the current minimum. KB-002 distinguishes **minimum5.4** from **recommended5.4.2**. This is a remaining policy-wording defect even though the string/citation checks passed.
- **OWN-02 onboarding:** the three replies use wording implying that five-business-day submission ensures day-one laptop availability. The cited source establishes the lead-time requirement, not an unconditional availability guarantee. Treat this qualification as a remaining grounding risk; do not claim all per-step statements are verified.
- **OWN-06** final three replies preserve VIP P1 and all four source-bound request fields with approval conditions; that does not erase the prior safe false refusal. PRN-07 PDF replies were manually checked and correct in this bounded review.

Next engineering work after user testing must correct minimum-versus-recommendation and onboarding qualification, add focused semantic regression assertions, then rerun relevant/full acceptance before any release. These are **not implemented fixes** at this checkpoint. The local browser is available with these limitations disclosed; mandatory acceptance is unresolved. Optional LLM-judge criteria remain skipped.
