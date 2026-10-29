# Supplemental dock verification ? 26 October 2026

S2-07 remains BLOCKED, awaiting instructor clarification. Its supplied input, expectations, injected fault and clarification safeguard are preserved. No instructor message sent. Exact conflict: [policy-conflict.md](policy-conflict.md). The supplemental case does not replace or waive S2-07.

## Changes

Separate evals/supplemental_cases.jsonl adds the same dock issue with the exact sentence ?I can continue working using the laptop screen.? A small impact parser extension recognizes ?can continue working? as stated usable service; it assigns no default priority to an unexplained dock failure. Custom workflow coverage asserts both the original unknown-impact clarification and explicit usable-service P3. evals/check_supplemental_result.py checks intermediate P3/hardware payload, retained requester context and approval in the unchanged runner's saved result. No supplied tests/cases/evaluator/dataset/services/dependency changes (39 baseline hashes verified).

## Actual verification

- Full offline: 101 tests, 99 passed, 2 live opt-ins skipped. Dataset: 1301 checks passed.
- Rebuilt local app image and restarted only app container, healthy. Source frozen before live verification and unchanged through all runs (source-before.json/source-after.json).
- Supplemental initial 1/1 and repeated 3/3 PASS. Each has hardware/P3 draft, no preapproval result, explicit approval, real create_ticket call, honest failure response and zero simulator tickets. Durable action errors confirm HTTP503 in all four attempts (supplemental-action.json, supplemental-repeated-actions.json). Draft payload and postapproval checks passed through the additional checker.
- Required unchanged 23-case suite x3: **65/69 (94.20%)**; repeats 22/23, 22/23, 21/23. S2-05 and S2-06 passed all three. S2-07 failed all three on the preserved missing-facts clarification. OWN-08 failed repeat3 before a draft on APIConnectionError; other two repeats passed. Trace and failed result retained. Focused OWN-08 retest passed, without changing the 65/69 result. Excluding S2-07 gives65/66 only as diagnostic information, not acceptance.
- check_kit initial read was run while OWN-09's deliberate status fault was active and returned503. It made a GET/status and may have consumed one injected fault count; OWN-09 still passed. This overlap is recorded rather than claiming complete test isolation. Sequential check_kit after all case runs passed (kit-final.log); no faults were cleared manually.
- Optional paid judge not run and not claimed passed. No release actions.

## Bounded semantic review

All three S2-03 replies distinguish minimum5.4/recommended5.4.2; all three OWN-06 drafts preserve VIP P1. OWN-02 preserves the5-business-day deadline and activation link to hiring manager, with no laptop-availability assurance. However, all three replies add a combined sentence beginning ?On the new starter's first day? and ending in remote delivery the business day before. This retains the actual before-start timing but violates the earlier separate-sentence clarity requirement. The existing guard misses ?first day?; no further source change was made during frozen verification. Automated OWN-02 passes do not establish full semantic acceptance. Actual replies are preserved in repeated.json. Supplemental claims also loosely attribute dock P3 to KB-010 before citing the governing KB-015; the P3 payload is justified by the explicit usable-service fact and KB-015, not a new default dock rule.

## Actual spending

Before: confirmed$1.61744880, retained reserved$0.02552396, available$0.85702724. After: confirmed$1.87511628, reserved$0.04033004, available**$0.58455368**. This task confirmed delta$0.25766748; new unknown reservation$0.01480608 from the connection failure retained. The69-case run has incomplete usage (one unknown billed call): no exact total/average cost is claimed; confirmed partial$0.22854488, unknown reserved$0.01480608. Case mean5.937s/p9515.437s; turn mean4.040s/p959.185s. Budget was not reset or unknown reservations released.

Full acceptance remains blocked. Current local Compose app/UI/simulator retained; no publish, push, tag, deployment or submission. Instructor clarification and residual semantic wording remain outstanding.
