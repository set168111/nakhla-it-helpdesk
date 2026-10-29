# Onboarding wording verification - 26 October 2026

## Final results

Only app/agent.py and custom tests/test_agent_workflow.py changed. The timing guard now recognizes "first day" as well as "day 1"/"day one". Its existing single correction now explicitly prohibits combining that opener with remote-before-start delivery and supplies separate source-supported timing sentences. Approval, priority and supplied tests remain unchanged.

Relevant final offline tests: **63/63 passed** (workflow and contract safety). Final live: **one targeted OWN-02 attempt, PASS**. Full actual reply in onboarding-final.json: local collection on day1 and remote delivery the business day before in separate sentences,5-business-day deadline, activation link to hiring manager, KB-012 citation and no availability promise. No draft or ticket. Final source unchanged during this live check. No full-suite rerun: the change is narrowly confined to KB-012 wording, so targeted verification is appropriate.

Earlier guard-only attempt is NOT hidden: onboarding.json records0/3, all safely withheld. Trace shows the correction removed the assurance but reintroduced the ambiguous combined sentence, exhausting the single allowed correction. The revised correction instruction resolved this on the final single attempt. These attempts used the same ledger and remain preserved. They are separate from the historical65/69 suite.

## Preserved acceptance score

| Historical repeat | Passed | Failed attempts |
|---|---|---|
|1|22/23|S2-07: missing-impact clarification leaves no draft for approval|
|2|22/23|S2-07: same|
|3|21/23|S2-07: same; OWN-08: APIConnectionError before candidate/draft|

Original result remains **65/69**, not a final-source full acceptance claim. OWN-08's later focused passing retest remains separate. Support decision and retrieval succeeded in its failed trace; next Support model call raised APIConnectionError, retaining a$0.01480608 unknown reservation. No completed candidate or approval/write was reached. Underlying connection cause is not recorded, so no DNS/TLS/provider-specific diagnosis is asserted and no retry/recovery feature was added. The trace-level model_calls0 reflects graph state not returned after failure; the recorded earlier successful call demonstrates that it does not mean no provider call occurred.

S2-07 remains **unresolved**, instructor clarification unavailable. KB-015 requires complete work blockage/no workaround for P2 or workaround/degraded-but-usable service for P3; the supplied dock input establishes neither. KB-010 gives dock steps but no default dock priority. The agent asks for clarification before drafting. Supplied case and priority safeguard unchanged. The separate explicit laptop-screen workaround case passed initial1/1 and repeated3/3; its503/approval/zero-ticket coverage **does not count as a pass for S2-07**.

Historical failures: ../supplemental-dock-2026-10-26/repeated.json; diagnosis trace: ../supplemental-dock-2026-10-26/own08-traces.json; separate OWN-08 retest: ../supplemental-dock-2026-10-26/own08-retest.json; supplemental503 results: ../supplemental-dock-2026-10-26/supplemental-repeated.json.

## KB-012 factual versus wording assessment

Original sentence: "On the new starter's first day, the laptop is collected locally at the IT Service Desk counter for onsite starters, or delivered by courier the business day before for remote starters."

KB-012 section2: local collection is day1; remote delivery is the business day before. The original sentence explicitly retained both correct dates, so a wrong delivery date was not established. Its first-day opener ambiguously scoped both clauses, violating the existing separate-sentence clarity rule. The confirmed defect was a guard synonym gap and insufficiently explicit correction, not a missing policy or permission to invent a guarantee. The final actual response separates the dates clearly. Source extracted from unchanged PDF: ../onboarding-source-text.txt.

## Docker and budget

Final app rebuilt/recreated and healthy;42 runtime files in running app container match host final source. App, simulator and UI HTTP200. Final check_kit REST/status and six-tool MCP inventory/owned lookup passed. Simulator/UI were not rebuilt or restarted; their packaged code remains unchanged. This verifies final local app source/startup/read wiring and targeted live behavior, not a new full-suite run or production approval. Docker progress on stderr causes PowerShell exit1 despite logged completed build/healthy startup; direct hashes/health establish outcome.

Final confirmed spent **$1.88611232**, retained unknown reserved **$0.04033004**, available **$0.57355764**. Final single live call confirmed cost$0.00442352; all clarity work including earlier failed probes$0.01099604. No reservation reset, paid judge, Git, release, submission or video actions.

## Simple manual retest

Open http://127.0.0.1:7860, start a new chat as tariq.hamdan@nakhla.example, and ask: "What should a new employee do before their first day, and when will they receive their laptop?" Check separate local-day1/remote-business-day-before sentences, no availability promise and KB-012 citation. Final manual retest PASSED as explicitly reported by the user on26October2026: clear separate laptop timings, complete answer and matching KB-012 Sources. No additional model call was made to record this result. S2-07 remains unresolved.


## Final user-reported manual pass

On26October2026 the user explicitly confirmed clear separate laptop timings, a complete answer and matching KB-012 Sources. The scoped onboarding manual requirement is passed. Historical65/69, the S2-07 gap, separate OWN-08 passing retest and supplemental503 results remain unchanged. App/runtime retained; documentation-only update. Next proposed milestone: remaining local manual impact/context and approval/rejection acceptance checks.


## Manual evidence reconciliation

The user explicitly reported all seven manual flows passed: VPNfollow-up/versions/citations; FinanceReject/freshApproveIT-2001; activeincident/no-duplicate; CRMcontext/nothing-tried; updatedimpact/freshP2/ApproveIT-2002; Approve disabled after success; finalonboarding/KB-012Sources. See ../final-verification-2026-10-26/manual-results.md. Earlier suggestions to repeat these passes are superseded. No new paid calls/tests/source changes. Outstanding submission work is portfolio finishing, peer clean-clone preflight, course/team/check-in evidence confirmation and separately authorized final deliverables. S2-07 remains unresolved; instructor clarification is not the next action.
