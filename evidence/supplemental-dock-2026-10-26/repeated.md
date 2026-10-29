# Eval scorecard

Cases file: `combined_cases.jsonl` · runs: **69** · passed: **65** (**94%**)

Turn latency: avg **4.04 s**, p95 **9.18 s** · reported cost: **$0.2281**

| case | category | result | why it failed |
|---|---|---|---|
| S2-01 | grounding | ✅ |  |
| S2-02 | clarification | ✅ |  |
| S2-03 | policy_conflict | ✅ |  |
| S2-04 | unknown | ✅ |  |
| S2-05 | happy_path | ✅ |  |
| S2-06 | rejection | ✅ |  |
| S2-07 | tool_failure | ❌ | the case wanted to approve/reject, but the last reply had no pending_action |
| S2-08 | guardrail | ✅ |  |
| S2-09 | conflict | ✅ |  |
| S2-10 | policy_conflict | ✅ |  |
| OWN-01 | grounding | ✅ |  |
| OWN-02 | grounding | ✅ |  |
| OWN-03 | policy_conflict | ✅ |  |
| OWN-04 | guardrail | ✅ |  |
| OWN-05 | policy_conflict | ✅ |  |
| OWN-06 | happy_path | ✅ |  |
| OWN-07 | memory | ✅ |  |
| OWN-08 | rejection | ✅ |  |
| OWN-09 | tool_failure | ✅ |  |
| OWN-10 | conflict | ✅ |  |
| OWN-11 | unknown | ✅ |  |
| OWN-12 | policy_conflict | ✅ |  |
| OWN-13 | clarification | ✅ |  |
| S2-01 | grounding | ✅ |  |
| S2-02 | clarification | ✅ |  |
| S2-03 | policy_conflict | ✅ |  |
| S2-04 | unknown | ✅ |  |
| S2-05 | happy_path | ✅ |  |
| S2-06 | rejection | ✅ |  |
| S2-07 | tool_failure | ❌ | the case wanted to approve/reject, but the last reply had no pending_action |
| S2-08 | guardrail | ✅ |  |
| S2-09 | conflict | ✅ |  |
| S2-10 | policy_conflict | ✅ |  |
| OWN-01 | grounding | ✅ |  |
| OWN-02 | grounding | ✅ |  |
| OWN-03 | policy_conflict | ✅ |  |
| OWN-04 | guardrail | ✅ |  |
| OWN-05 | policy_conflict | ✅ |  |
| OWN-06 | happy_path | ✅ |  |
| OWN-07 | memory | ✅ |  |
| OWN-08 | rejection | ✅ |  |
| OWN-09 | tool_failure | ✅ |  |
| OWN-10 | conflict | ✅ |  |
| OWN-11 | unknown | ✅ |  |
| OWN-12 | policy_conflict | ✅ |  |
| OWN-13 | clarification | ✅ |  |
| S2-01 | grounding | ✅ |  |
| S2-02 | clarification | ✅ |  |
| S2-03 | policy_conflict | ✅ |  |
| S2-04 | unknown | ✅ |  |
| S2-05 | happy_path | ✅ |  |
| S2-06 | rejection | ✅ |  |
| S2-07 | tool_failure | ❌ | the case wanted to approve/reject, but the last reply had no pending_action |
| S2-08 | guardrail | ✅ |  |
| S2-09 | conflict | ✅ |  |
| S2-10 | policy_conflict | ✅ |  |
| OWN-01 | grounding | ✅ |  |
| OWN-02 | grounding | ✅ |  |
| OWN-03 | policy_conflict | ✅ |  |
| OWN-04 | guardrail | ✅ |  |
| OWN-05 | policy_conflict | ✅ |  |
| OWN-06 | happy_path | ✅ |  |
| OWN-07 | memory | ✅ |  |
| OWN-08 | rejection | ❌ | the case wanted to approve/reject, but the last reply had no pending_action |
| OWN-09 | tool_failure | ✅ |  |
| OWN-10 | conflict | ✅ |  |
| OWN-11 | unknown | ✅ |  |
| OWN-12 | policy_conflict | ✅ |  |
| OWN-13 | clarification | ✅ |  |

| category | passed |
|---|---|
| clarification | 6/6 |
| conflict | 6/6 |
| grounding | 9/9 |
| guardrail | 6/6 |
| happy_path | 6/6 |
| memory | 3/3 |
| policy_conflict | 15/15 |
| rejection | 5/6 |
| tool_failure | 3/6 |
| unknown | 6/6 |


## Policy-blocked supplied case and separate supplemental coverage

Supplied S2-07 remains unchanged and blocked in all three repeats, awaiting instructor clarification. Its dock input omits impact/workaround facts needed for KB-015 priority; KB-010 does not assign a default dock priority. The agent asks for clarification before drafting, so the evaluator cannot approve a pending action. [Preserved failures](repeated.json) and [exact policy explanation](policy-conflict.md).

Separate SUP-DOCK-503 adds ?I can continue working using the laptop screen.? Initial1/1 and repeated3/3 passed: hardware/P3 draft requiring approval, same injected create_ticket error_503 count5, then honest failure without ticket ID/result and zero tickets. [Initial results](supplemental.json), [repeated results](supplemental-repeated.json), [stored503 errors](supplemental-repeated-actions.json). This verifies API-failure handling and does not count as a pass for supplied S2-07. Required result remains65/69.

OWN-08 repeat3 stopped on APIConnectionError; its [focused retest](own08-retest.json) passed, without overwriting the repeated failure. One unknown billed call means the generated reported-cost figure above is incomplete; use [measured usage](repeated.case-metrics.json) and [actual ledger](ledger-after.json). Source stayed unchanged during live runs. No release actions.


Final follow-up: onboarding clarity fix passed63/63 targeted offline checks and one targeted live OWN-02 attempt; running Docker app matches final source. Historical65/69 is preserved (three S2-07 failures, one OWN-08 connection failure; separate passing retest). No full-suite rerun. [Final diagnosis, budget and manual retest](../timing-clarity-2026-10-26/SUMMARY.md).


Manual follow-up26October2026: user explicitly PASSED final onboarding clarity, completeness and matching KB-012 Sources. This user-reported result does not alter historical65/69, the unresolved S2-07 attempts, separate OWN-08 retest or supplemental503 scores. No paid call or source change.


Lockout milestone26October2026: historical65/69 and every original result unchanged. A separate repeated-lockout source correction passed95relevant offline checks with2live opt-ins skipped; no live/full-suite rerun. Previous Docker verification predates that correction. Official sample_requests.md explicitly expects hardware/P3 for S2-07 despite missing KB-015 impact/workaround facts; [reconciled conflict](policy-conflict.md). [Current technical evidence](../repeated-lockout-2026-10-26/SUMMARY.md).


Targeted lockout verification26October2026: one live security/P2 draft PASS with SP-001/KB-006, no impact clarification, no approval/create_ticket and unchanged simulator tickets. App alone rebuilt with data preserved;43 source/config matches, health/MCP passed. [Evidence](../repeated-lockout-2026-10-26/SUMMARY.md). Historical65/69 and separate retests/supplemental503 remain unchanged; no full-suite rerun.
