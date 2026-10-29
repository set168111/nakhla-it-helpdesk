# Approval-time incident and publication ignore corrections

26 October 2026. Scoped offline work only; no paid calls, service changes, real ticket writes, full-suite rerun or Git mutations.

## Confirmed findings and minimal corrections

Read-only `git check-ignore -v --no-index` confirmed the unanchored `data/` rule excluded services/data/employees.json and services/data/status.json. Changed only that rule to `/data/`. [Before](ignore-before.txt) is a labelled transcription of actual tool output; [after](ignore-after.redacted.txt) includes explicit nonmatching seed paths and matching root runtime paths. SQLite exclusions also remain. Package seeds are byte-identical to working seeds; [package ignore evidence](package-ignore.redacted.txt) confirms seed eligibility and runtime exclusion in the clean copy.

Approval already reads directory and live service status separately from drafting. The new ordinary late-incident regression passed before runtime changes: the pending action becomes superseded, the incident ID is reported, replay/retry cannot write, and zero write calls occur.

Recovery already retains unknown status and prevents a replacement draft, but hid the matching incident behind its generic exception reply. [Regression before](incident-before.redacted.log) records that reporting failure. The incident branch now explicitly reports the incident and earlier unknown outcome, sends zero additional writes, and retains the immutable action/key for reconciliation. It never claims the earlier attempt created no ticket. Recovery tests verify unchanged payload/hash, replacement blocking, and same-key reconciliation after the incident clears, followed by replay blocking.

A separate [failing workflow regression](code-regression-before.redacted.log) demonstrated a real bypass: NX-503 past the 3000-character description boundary plus a code-free model subject produced a frozen payload without the documented code; a newly active incident then allowed a fake write. Source context retains the code, but immutable payload previously did not. A small drafting-only description helper now reserves space for the context code when absent. Both Support/Reviewer preview and final immutable payload use it; approval still independently reads live status and checks only the frozen payload. No mutable-session fallback was added to approval. Reviewer preview equality and the 3000-character bound are asserted.

## Actual offline verification

- Approval module: 19 tests, 17 passed, 2 live opt-ins skipped ([log](test_approvals.py.redacted.log)).
- Workflow module: 58 passed ([final log](workflow-final.redacted.log)).
- Contract safety module: 8 passed ([log](test_contract_safety.py.log)).
- Total relevant module checks: 83 passed, 2 skipped; not a full-suite rerun.
- All manifest-documented codes pass extraction, bounded description retention and immutable-payload incident matcher compatibility ([code check](documented-code-check.json)).

Initial fixture errors (`network` instead of schema `network_access`) and an intermediate description-length failure are retained in original logs; these are not claimed as product failures. Final results supersede intermediate failures. Test doubles are explicitly offline and prove no provider/model quality or live simulator outcome.

## Remaining verification

Docker and isolated fresh-start proof predate changes to app/agent.py and app/approvals.py. Running services/images were not changed or reverified. Current-source Docker/runtime and independent peer checks remain pending. Historical evaluation results and costs are unchanged. Package manifest/link/anchor/privacy/source checks are refreshed separately; a static package pass does not establish Docker/runtime acceptance.
