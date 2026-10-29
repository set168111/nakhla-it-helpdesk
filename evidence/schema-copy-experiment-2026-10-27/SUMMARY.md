# Textual-schema removal experiment - 27 October 2026

Recommendation: **retain the working baseline; do not promote the candidate**. Candidate and full baseline backup remain private. This is a six-turn exploratory result, not current-source Docker verification.

## Scope and preservation

Only candidate app/agent.py removes the textual schema-serialization line; native structured output and local validation remain unchanged. Baseline and candidate source hashes are retained in setup-private.json and private-source-hashes-after.json. Working source, simulator, data/index/traces, clean package and all historical evidence are unchanged. Private copies use copied cached indexes, fresh local state and separate experiment ledgers. No ingestion. One independent MCP process per chat, fresh runtime per turn; a private loopback simulator on8114 served both arms. Comparison uses the production /api/chat handler through ASGI transport; it is not browser/UI or Docker runtime timing.

Offline before paid calls: **83 passes and2 live opt-in skips per arm**. A fake transport exercised production _model and confirmed unchanged native schemas, model settings, packets and local validation for Decision, Candidate, Review and ClaimsRevision. See offline-module-results.json and offline-schema-comparison.json.

Actual ledger check included a fresh read of the working database and a read-only copy of the retained stopped isolated-container ledger. Docker Desktop startup and specific OpenRouter egress were explicitly user-authorized. Model/embedding destination and fictional source scope were verified; credentials were passed only through private process environment, never copied into source or printed. See aggregate-before.json and egress-review.json.

## Results

All deltas below are candidate minus baseline. Costs include model and query embedding, provider-reported actual amounts. No new unknown reservations and no calculated-cost fallback.

| Scenario | Calls B/C | Input tokens B/C (delta; %) | Output tokens B/C (delta; %) | Seconds B/C (delta; %) | Actual cost USD B/C (delta; %) | Corrections B/C |
|---|---|---|---|---|---|---|
| NX781 | 3/3 | 14513/13364 (-1149; -7.92%) | 377/373 (-4; -1.06%) | 16.203/12.297 (-3.906; -24.11%) | 0.00640976/0.00594346 (-0.00046630; -7.27%) | 0/0 |
| PDF | 4/4 | 14733/13746 (-987; -6.70%) | 409/453 (+44; +10.76%) | 13.015/12.860 (-0.155; -1.19%) | 0.00654870/0.00622430 (-0.00032440; -4.95%) | 1/1 |
| Finance | 3/3 | 12527/11696 (-831; -6.63%) | 295/310 (+15; +5.08%) | 10.469/8.531 (-1.938; -18.51%) | 0.00548364/0.00517512 (-0.00030852; -5.63%) | 0/0 |

Totals: input41773 ->38806 (-2967; -7.10%); output1081 ->1136 (+55; +5.09%); actual cost$0.01844210 ->$0.01734288 (-$0.00109922; -5.96%); measured turn time39.687 ->33.688seconds (-5.999; -15.12%). Calls10 ->10 and corrections1 ->1. Per-call/role tokens, latency, actual cost, embedding time, MCP startup and response-quality predicates are recorded in comparison.json and the six individual response files.

## Quality, failures and limitations

Both NX-781 answers distinguish minimum5.4 from recommended5.4.2 and cite current KB-002/SP-002. Both onboarding answers give5businessdays, hiring-manager activation delivery, local day1 collection and remote courier the business day before; both initially triggered the retained timing guard and used one correction. Both Finance drafts are byte-equivalent as payload objects: security/P2, correct requester/department/error and truthful immediate-escalation history. Native schemas and local guards remain active.

Explicit predicates passed for all6responses, but manual review identifies candidate presentation/wording concerns: PDF prose exposes internal chunk IDs; Finance prose generalises security-category routing into security-incident language. Do not interpret this as an established active security incident or silently declare all quality identical. See manual-quality-review.json. No additional fix or retest was performed.

Retrieval code/configuration stayed unchanged, but model-selected queries can change results: NX-781 selected35baseline vs34candidate chunks (baseline additionally KB-010:2:dcd7f1b4b4); PDF selected the same30chunks in the same order; Finance selected the same27chunks in a different order. Therefore observed token/cost differences cannot be attributed exclusively to the removed schema bytes. All recorded provider cache-read tokens were zero. Latency includes cold app setup and initial pricing lookup, excludes separately recorded MCP startup and retrieval initialization; network/provider variation and order remain confounders. **Six turns cannot establish a reliable p95 or consistent speed improvement.** No claimed throughput or broad quality improvement.

Retained preflight interruptions: Docker engine initially off; direct private-ledger copy permissions failed; resolved with authorized Desktop start and Admin-only access to the new private directory. Two automatic approval-review launch rejections occurred before any paid execution; user explicitly approved specific fictional-data egress, then the same bounded experiment ran. A post-run read-only summary initially failed under sandbox permissions; rerun with access to the private runtime ledgers, with no additional provider call. These are preparation/reporting failures, not hidden successful performance runs.

## Budget and shutdown

Experiment actual cost **$0.03578498**, unknown **$0**, below the$0.12 cap. Every turn remained below$0.02 including reservations. Existing unknown reservations **$0.04033004** remain retained. Aggregate confirmed **$1.94088480**, aggregate remaining **$0.51878516** of$2.50. Future budget reads must include both private experiment ledgers (or their retained snapshots) plus the stopped isolated-ingestion ledger; the working-only ledger intentionally remains unchanged.

The simulator audit has0tickets and onlyGETrequests: no approvals, resets, ticket writes or notes. Only the experiment-owned process tree was stopped;8114is closed and working project containers remain stopped. Docker Desktop engine is left available; no global shutdown was attempted. Data, caches, private baseline/candidate, ledgers, traces and failures are retained. See simulator-final-audit.json, isolated-service-cleanup.json and shutdown-verification.json.

No candidate promotion, working runtime edits, other optimisation, Git, publication or release action. Current-source Docker verification remains pending.
