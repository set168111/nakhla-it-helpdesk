# Current submission copy - 5 November 2026

Use [submission status](docs/submission-status.md) and [README](README.md) for current login/setup and limits.
Case19 is user-verified including wording; Case20 is incomplete/code deferred.
Default simulator 8102 is unpublished; admin pages require separate login.
The dated observations below remain historical and are not current setup,
accounting, peer-preflight or authenticated acceptance claims. 65/69 is retained.

<details><summary>Original publication checkpoint observations (historical)</summary>

# Tasks - local user-testing checkpoint

> **Publication status (29 October 2026):** this file is a dated working record from local development and is kept for provenance. Statements below such as "latest", "paused", "resume", local paths (including `local-packages/nakhla-it-helpdesk`) and 127.0.0.1 service state describe the original development machine, not this repository or a fresh clone. Public repository: https://github.com/set168111/nakhla-it-helpdesk (the course submission repository created from this package). The demo video segments exist; final assembly and upload are pending. No peer review or instructor approval is claimed, and supplied course-kit material is included under the assignment's instruction to copy the kit into a public project repository, keeps its own notices, and is not covered by the project's scoped MIT grant (see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)). Current setup instructions are in [README.md](README.md).

**Latest runtime verification - 27 October 2026:** current working baseline retained; optimisation stopped and schema-removal candidate not promoted. App-only Docker rebuild/recreation passed;43runtime/config hashes match; cached20-document/100-chunk startup, health, actual MCP reads and UI connectivity passed. **10focused in-container mocked approval/incident regressions passed** with temporary state and test networking blocked. No paid calls, simulator resets, approvals or real ticket writes; no full-suite rerun. Durable data/indexes/ledgers/traces remain byte-identical, sessions/actions494/159. UI http://127.0.0.1:7860; existing simulator/UI containers were started without rebuilding. This supersedes earlier current-source Docker-pending/shutdown statements below; older isolated fresh-start and peer preflight remain distinct. Historical scores are unchanged. Aggregate remaining **$0.51878516**, including retained reservations and experiment ledgers. [Verification and remaining gaps](evidence/docker-approval-incident-2026-10-27/SUMMARY.md), [actual accounting](evidence/docker-approval-incident-2026-10-27/aggregate-budget-after.json).


**Shutdown-only reconfirmation - 26 October 2026:** all three project containers remain stopped; no new stop was necessary. Zero listeners on project/isolated ports and zero native project Python/uvicorn processes. [Identity/status evidence](docs/EVIDENCE-COPY-NOTICE.md#excluded-local-history). Actual working ledger reread mode=ro: confirmed $1.90487596, unknown reserved $0.04033004, 1617 rows. Including retained isolated charge, aggregate confirmed **$1.90509982**, unknown **$0.04033004**, remaining **$0.55457014**. [Latest budget](docs/EVIDENCE-COPY-NOTICE.md#excluded-local-history). Latest fixes/evidence and 83 passes/two skips plus all 24 code checks remain recorded below; clean package static pass retained. Docker/fresh-start proof predates runtime changes. **Next step: current-source Docker runtime verification, preserving data; no automatic full-suite rerun.** No fixes, tests, paid calls, Git/release actions, data deletion or package refresh during this shutdown. Remain paused until user resumes.


## PAUSED for today ? 26 October 2026, latest continuation checkpoint

User explicitly paused: no further fixes, tests, paid calls, Git/release actions or automatic resumption. This checkpoint supersedes earlier running-service and current-source runtime verification claims below.

**Completed:** anchored `.gitignore` runtime exclusion to `/data/`; required services/data/employees.json and status.json remain publishable. Added late-incident approval coverage: ordinary drafts supersede with zero writes; uncertain/reconciling actions report the incident honestly while retaining unknown outcome, replacement-draft blocking and same-key recovery. A failing regression proved truncation could omit NX-503 from immutable payloads and bypass incident matching. Minimal drafting correction retains the context code in the bounded description used by Reviewer preview and final frozen payload. Approval independently rechecks live status; drafting and approval revalidation remain separate. Runtime changes are limited to app/agent.py and app/approvals.py.

**Verification retained:** 83 offline passes, two live opt-ins skipped; all 24 documented codes passed compatibility checks. Relevant modules only, no full-suite rerun. [Fixes, regressions and evidence index](evidence/approval-incident-2026-10-26/SUMMARY.md), [current source snapshot](evidence/approval-incident-2026-10-26/source-current.json), [24-code check](evidence/approval-incident-2026-10-26/documented-code-check.json).

**Clean package:** refreshed at local-packages/nakhla-it-helpdesk; manifest, file/link/anchor/privacy and current working-source copy checks passed. [Static report](docs/EVIDENCE-COPY-NOTICE.md#excluded-local-history), [provenance](docs/EVIDENCE-COPY-NOTICE.md#excluded-local-history). Package and previous evidence were preserved during pause, not refreshed again. **Docker and isolated fresh-start verification predate the latest runtime changes** and do not verify current source. No further tests were run while saving this pause.

**Actual budget read:** SQLite URI mode=ro, no application/provider calls. Working ledger: confirmed **$1.90487596**, retained unknown reservations **$0.04033004**, 1617 rows; calculated cost $0.00000000. Retained isolated-ingestion snapshot adds **$0.00022386** confirmed, no unknown reservations. Aggregate confirmed **$1.90509982**, unknown **$0.04033004**, remaining **$0.55457014** of $2.50. Isolated charge comes from its retained snapshot, not a fresh volume read; working ledger was reread unchanged after shutdown. [Budget timestamp/accounting](docs/EVIDENCE-COPY-NOTICE.md#excluded-local-history). Never reset the ledger, discard unknown reservations or treat the isolated volume as a fresh budget.

**Services STOPPED:** only `nakhla-helpdesk` UI, app and helpdesk-api containers stopped, after verifying Compose project, workspace/config path and service labels. Used docker stop on exact verified IDs, no down/removal/volume deletion. Zero project containers running; no listeners remain on 7860/8000/8102 or isolated 7861/8001/8104, and no matching native project Python/uvicorn processes remain. Native PID-file stop helper was not used against Docker processes. Containers retained; all preexisting data/ files (databases, index and traces) remain byte-identical across shutdown. Package, images, named volumes and prior evidence retained. Simulator-created tickets are in-memory and are not guaranteed to survive restart. [Identity-safe shutdown](docs/EVIDENCE-COPY-NOTICE.md#excluded-local-history), [listeners](docs/EVIDENCE-COPY-NOTICE.md#excluded-local-history), [native processes](docs/EVIDENCE-COPY-NOTICE.md#excluded-local-history), [data preservation](docs/EVIDENCE-COPY-NOTICE.md#excluded-local-history).

**Exact resume step:** resume targeted current-source Docker rebuild and runtime verification, preserving existing data; no automatic full-suite rerun. First reread this checkpoint and actual budget, verify existing data mount/cached index and stopped container identities. Build only the changed app image with `docker compose -p nakhla-helpdesk build app`, then resume the existing project using `docker compose -p nakhla-helpdesk up -d --no-build`. Verify current-source hashes, cached startup, health and bounded targeted approval/incident runtime behavior. Do not reset data, recreate a fresh budget, re-ingest on a cache miss or make paid model calls without renewed authorization. Save new runtime proof separately from historical Docker/fresh-start evidence. No execution until the user resumes.

---


**26 October 2026 approval/incident correction:** `/data/` now excludes only root runtime data, keeping required simulator seeds publishable. Relevant offline modules: **83 passed, 2 live opt-ins skipped**. Focused offline regressions confirm late-incident supersession with zero writes; uncertain recovery reports the incident while retaining unknown outcome, replacement-draft blocking and the same immutable action key. A failing regression proved long issue truncation could remove NX-503 and bypass approval-time incident matching; bounded drafting description now retains the context code in both reviewer preview and immutable payload. Drafting and approval revalidation remain separate. Docker/fresh-start verification predates these runtime changes; current images/running services have not been changed or reverified. No paid calls, service actions, full-suite rerun or Git mutations. See [focused evidence](evidence/approval-incident-2026-10-26/SUMMARY.md).


## Current milestone - 26 October 2026

**README category-table clarification - 26 October 2026:** historical category counts now have explicit pass rates and a 65/69 total, with underlying results/metrics links. Whole-case and turn latency are labelled separately; confirmed partial cost, retained unknown reservation and unavailable exact total/average remain distinct. All three S2-07 failures, OWN-08 connection failure, separate passing retest and supplemental 503 results are preserved. Documentation/package refresh only; no evaluation, paid call, application or service change. Independent peer preflight remains uncompleted; no administrative approval or relicensing permission is claimed.

**Isolated fresh-start PASS - agent-run, not peer:** 20 documents/two PDFs/100 chunks; 43 runtime files matched; health, MCP reads, UI connectivity and cached restart passed. Only isolated services stopped; working app/data untouched. One actual embedding charge $0.00022386; aggregate remaining $0.55457014, including retained unknown $0.04033004. Future budget reads must include the retained isolated ledger. [Results and accounting](evidence/isolated-fresh-start-2026-10-26/SUMMARY.md). Independent peer preflight remains UNCOMPLETED.

**Local package assembled - 26 October 2026:** `local-packages/nakhla-it-helpdesk` contains a separate cleaned copy. Static manifest/file/link/anchor/privacy review passed at assembly. The subsequent agent-run fresh-start check passed as recorded above; independent peer preflight is uncompleted. Application source and all43 previously verified runtime/config files are byte-identical in the package. Reviewed evidence copies are labelled; four logs have `.redacted` names. Supplied guidance/visuals are replaced by official-source pointers, five unrelated Capstone documents and the backup REQUIREMENTS.md are excluded, and originals remain local. MIT is limited to identified original contributions; supplied/adapted material keeps separate provenance. Broader kit redistribution/relicensing permissions remain unconfirmed.

**Latest rejection manual PASS - user-reported:** draft cleared, Nothing was written and no tool calls. This follows the earlier manually observed awaiting-approval state; it is not an automated replay or a claim that the original saved API action was changed. No approval or creation is claimed.

**Repeated-lockout manual PASS - user-reported26October2026:** security/P2, SP-001 and KB-006 Sources, exact attempted step ("I already checked saved passwords on my devices and found none."), no unnecessary clarification and awaiting approval. No approval/creation is claimed. This is separate from the automated live API result; no tests or paid calls were repeated to record it.

**Local package assembled; presentation scripts not executed:** [publication file list](docs/publication-files.md) and exact manifest, three-minute video script and six-minute live demo/Q&A (`docs/video-script.md` and `docs/demo.md`, historical references; these two planning pages are omitted from this publication copy) and future-only fault commands. The completed [portfolio video](<assets/video/Nakhla IT Helpdesk portfolio.mp4>) was added to this repository later. No peer contact, reset, rehearsal, recording, publication, Git, tag or submission. All known limitations and solo/AI/kit attribution retained.

Current scoped finding: repeated unexplained daily lockouts were incorrectly routed to identity_access with priority unset. The minimal KB-006/SP-001 correction now assigns security/P2 without unrelated impact clarification. Count, one-day timeframe and unknown cause must be present; existingP1 rules remain higher. Source changes are limited to app/helpdesk_policy.py, app/agent.py and custom tests/test_agent_workflow.py.

**Verification:** two focused regressions failed before and passed after; relevant offline checks **95passed,2live opt-ins skipped (97total)**. Later single targeted live lockout check passed; no full-suite rerun. [Lockout fix and offline evidence](evidence/repeated-lockout-2026-10-26/SUMMARY.md).

**Runtime verified:** app alone rebuilt/restarted with data preserved;43 workspace/container source/config files match current source. App/simulator/UI healthHTTP200 and container six-tool MCP inventory/directory/status reads passed. One live security/P2 draft check passed with SP-001/KB-006 citations and no impact clarification. No approval or create_ticket sent; simulator/UI untouched. UI http://127.0.0.1:7860. [Evidence](evidence/repeated-lockout-2026-10-26/SUMMARY.md).

**Preserved results:** historical65/69, repeats22/23,22/23,21/23 (three S2-07 failures and one OWN-08 connection failure); later OWN-08 pass and supplemental503 initial1/1+repeated3/3 remain separate. Supplemental503 does not pass supplied S2-07. Final onboarding targeted63offline+one livePASS and the seven earlier user-reported manual passes remain scoped historical evidence. The new lockout manual PASS is recorded separately below. [Manual passes](evidence/final-verification-2026-10-26/manual-results.md).

**Completed portfolio work:** README screenshot, architecture/startup links, real/simulated table, category results, failure/fix narrative, acknowledgements and confirmed solo contributions are complete. Sari Tahhan performed project decisions, directed/reviewed AI-assisted implementation, manually tested and validated fixes; Codex/ChatGPT assisted design/code/debugging/documentation. Peer checklist prepared, not performed.

**Still outstanding:** independent fresh-clone preflight; unverified registration/DESIGN review/check-ins and unresolved solo-versus-pair course requirement; separately authorized public product repo/clean publication review/tag/video/live demo/submission. No peer/trainer approval is claimed. Optional judge, cloud/Jira/A2A/production features and capstone optimisation are not mandatory mini-project work. The assignment does not prescribe100% supplied-case success or another full repeated run.

**S2-07:** official sample_requests.md explicitly expects hardware/P3, while the supplied input omits impact/workaround facts required by KB-015 and KB-010 has no default dock priority. Supplied case and clarification remain unchanged. [Exact conflict](evidence/supplemental-dock-2026-10-26/policy-conflict.md). Instructor clarification is unavailable, not the next required action.

**Historical lockout-verification budget snapshot:** confirmed$1.89905922, retained unknown$0.04033004, available$0.56061074. One authorized live chat cost$0.00583914; app alone rebuilt/restarted, no source edits in this verification phase. No approval/create_ticket, full-suite rerun, unrelated work, Git or release actions.

## Current task list

- [x] Confirm repeated-lockout defect with failing offline regressions.
- [x] Apply documented security/P2 rule with P1/context/approval checks.
- [x] Run relevant offline checks and reconcile current records.
- [x] Finish portfolio README and confirm truthful solo/AI attribution.
- [x] Record all reported manual passes, including lockout awaiting approval and the later rejection; no automated replay.
- [x] Verify rebuilt app/source/health/MCP and one live security/P2 draft; leave unapproved.
- [ ] Peer fresh-clone preflight and existing course-evidence confirmation.
- [x] Prepare publication file list, video/live-demo scripts and future fault commands.
- [x] Assemble separate clean local package and verify static manifest/evidence/local documentation links.
- [x] Authorized isolated agent-run fresh-start, cached restart and cleanup; actual costs retained in aggregate accounting.
- [ ] Independent peer preflight and separately authorized final repository/video/demo/tag/submission execution.



_Publication current-section extract; historical evidence retained._

</details>
