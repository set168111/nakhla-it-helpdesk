# Final verification scorecard - 26 October 2026

**Status: acceptance blocked.** Source and supplied cases remained unchanged across the complete run. No failures removed or tests weakened. No feature/release work performed.

23 cases (10 supplied +13 original), three repeats: **60/69 (86.96%)**, repeats20/23 each. Supplied runner exit **1**. Runtime: current Docker Compose images, Python3.12.15.

| Check | Actual result |
|---|---|
| Full offline suite | 98 passed,2 live opt-ins skipped;100 total |
| Dataset validator | 1,301 checks passed |
| Current-source Compose build/startup | Passed; app/simulator healthy, UI HTTP200 |
| Cached app restart | Passed; persisted ready index reused, no paid calls |
| Container dependency consistency | pip check passed |
| Container/host source integrity | 43 runtime-source files match; no missing/mismatched files |
| Frozen source integrity | All61 recorded source/case/pin/packaging files unchanged |
| Real Linux stdio MCP | Six tools discovered, status/directory reads passed |
| Corpus/index | 20 docs including2PDF,100 ready real-embedding chunks |
| Compose UI queue -> app -> MCP | Error-code clarification passed; no model/embedding spending |
| Human onboarding retest | User explicitly passed laptop timing and KB-012 citation only |

Whole-case wall time: mean **4.526s**, nearest-rank p95 **7.942s**. Turn wall time: mean **3.239s**, p95 **7.157s**. Whole-case durations include setup/turns/assertions; small samples are not an SLA. No optimisation claim.

Suite cost **$0.21507326**, mean per attempted case **$0.00311700** including failures. Usage complete for observed turns; no new unknown billing. No paid judge. Existing unknown reservations retained. Project spent **$1.59377602**, reserved **$0.02552396**, remaining **$0.88070002** of$2.50. Startup/cached restart/free UI smoke made no paid calls.

## Mandatory failures - unresolved

| Case | Repeats failed | Actual response / failure |
|---|---|---|
| S2-05 | 3/3 | Is there a workaround or can you still use the service? [KB-015] Runner expected a pending draft for approval/rejection. |
| S2-06 | 3/3 | Are you completely blocked from working, and is there a workaround or can you still use the service? [KB-015] Runner expected a pending draft for approval/rejection. |
| S2-07 | 3/3 | Are you completely blocked from working, and is there a workaround or can you still use the service? [KB-015] Runner expected a pending draft for approval/rejection. |

The newer missing-impact/workaround gate caused these safe clarifications, but they remain failed mandatory scenarios. S2-05 cannot reach its expected approved P2 ticket, S2-06 cannot reach rejection, and S2-07 cannot exercise its expected create-failure path in this suite. Existing other approval/error tests do not waive these cases. Reconcile the required case flows with accurate priority/fact gathering without weakening safety or silently changing supplied cases; no fix was made during this frozen verification.

## Semantic/manual review boundary

Independent review sampled all three repeats of S2-03, OWN-02 and OWN-06 plus all nine failures. S2-03 distinguishes minimum5.4 from recommended5.4.2; OWN-06 preserves VIP P1 and requester facts. OWN-02 still says "ensure timely preparation, including laptop availability." This does not explicitly promise day1 availability, but may overstate KB-012 and remains a qualification risk despite string/citation assertions passing. Human laptop-timing/citation approval is preserved separately; it is not a blanket semantic pass.
Optional shared-runner --judge criteria were skipped, not scored as passes. Read-only independent review is bounded, not an automated judge or instructor approval. Instructor review remains not completed/approved/waived.

## Evidence and runtime

Raw cases/replies/failures: scorecard.json and scorecard.md; timing/cost/source metadata: scorecard.case-metrics.json. Independent scope/findings: independent-final-review.md. Manual outcomes: manual-results.json/.md. Startup/source/UI proof: compose-startup-verification.json, compose-cached-restart-verification.json, compose-source-integrity.json, compose-ui-queue-smoke.json. Source manifests: source-at-start.json and source-at-end.json. Prior failures and the data/simulator backup remain preserved.
Current Compose app, simulator and UI remain running on8000/8102/7860. Native PID files are stale and are not container identifiers. Stop only this Compose project with `docker compose -p nakhla-helpdesk stop`; restart with `docker compose -p nakhla-helpdesk up -d --no-build --wait`. No deployment/publish/push/tag/submission/video was performed. The evaluation resets fictional simulator tickets between cases; pre-verification simulated tickets and SQLite/index/traces were backed up. Do not restore an older spending ledger to roll back paid usage.

Next engineering step: address the nine mandatory case-flow failures and the residual onboarding wording under a separately authorised change, then rerun affected/full acceptance on the new frozen source. Human priority/context confirmations and final deliverables remain pending.
