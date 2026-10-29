# Accepted design - local user-testing checkpoint

> **Publication status (29 October 2026):** this file is a dated working record from local development and is kept for provenance. Statements below such as "latest", "paused", "resume", local paths (including `local-packages/nakhla-it-helpdesk`) and 127.0.0.1 service state describe the original development machine, not this repository or a fresh clone. Public repository: https://github.com/set168111/nakhla-it-helpdesk (the course submission repository created from this package). The demo video segments exist; final assembly and upload are pending. No peer review or instructor approval is claimed, and supplied course-kit material is included under the assignment's instruction to copy the kit into a public project repository, keeps its own notices, and is not covered by the project's scoped MIT grant (see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)). Current setup instructions are in [README.md](README.md).

**Latest runtime verification - 27 October 2026:** current working baseline retained; optimisation stopped and schema-removal candidate not promoted. App-only Docker rebuild/recreation passed;43runtime/config hashes match; cached20-document/100-chunk startup, health, actual MCP reads and UI connectivity passed. **10focused in-container mocked approval/incident regressions passed** with temporary state and test networking blocked. No paid calls, simulator resets, approvals or real ticket writes; no full-suite rerun. Durable data/indexes/ledgers/traces remain byte-identical, sessions/actions494/159. UI http://127.0.0.1:7860; existing simulator/UI containers were started without rebuilding. This supersedes earlier current-source Docker-pending/shutdown statements below; older isolated fresh-start and peer preflight remain distinct. Historical scores are unchanged. Aggregate remaining **$0.51878516**, including retained reservations and experiment ledgers. [Verification and remaining gaps](evidence/docker-approval-incident-2026-10-27/SUMMARY.md), [actual accounting](evidence/docker-approval-incident-2026-10-27/aggregate-budget-after.json).


## Current milestone - 26 October 2026

**Isolated fresh-start PASS - agent-run, not peer:** 20 documents/two PDFs/100 chunks; 43 runtime files matched; health, MCP reads, UI connectivity and cached restart passed. Only isolated services stopped; working app/data untouched. One actual embedding charge $0.00022386; aggregate remaining $0.55457014, including retained unknown $0.04033004. Future budget reads must include the retained isolated ledger. [Results and accounting](evidence/isolated-fresh-start-2026-10-26/SUMMARY.md). Independent peer preflight remains UNCOMPLETED.

**Local package assembled - 26 October 2026:** `local-packages/nakhla-it-helpdesk` contains a separate cleaned copy. Static manifest/file/link/anchor/privacy review passed at assembly. The subsequent agent-run fresh-start check passed as recorded above; independent peer preflight is uncompleted. Application source and all43 previously verified runtime/config files are byte-identical in the package. Reviewed evidence copies are labelled; four logs have `.redacted` names. Supplied guidance/visuals are replaced by official-source pointers, five unrelated Capstone documents and the backup REQUIREMENTS.md are excluded, and originals remain local. MIT is limited to identified original contributions; supplied/adapted material keeps separate provenance. Broader kit redistribution/relicensing permissions remain unconfirmed.

**Latest rejection manual PASS - user-reported:** draft cleared, Nothing was written and no tool calls. This follows the earlier manually observed awaiting-approval state; it is not an automated replay or a claim that the original saved API action was changed. No approval or creation is claimed.

Current scoped finding: repeated unexplained daily lockouts were incorrectly routed to identity_access with priority unset. The minimal KB-006/SP-001 correction now assigns security/P2 without unrelated impact clarification. Count, one-day timeframe and unknown cause must be present; existingP1 rules remain higher. Source changes are limited to app/helpdesk_policy.py, app/agent.py and custom tests/test_agent_workflow.py.

**Verification:** two focused regressions failed before and passed after; relevant offline checks **95passed,2live opt-ins skipped (97total)**. Later single targeted live lockout check passed; no full-suite rerun. [Lockout fix and offline evidence](evidence/repeated-lockout-2026-10-26/SUMMARY.md).

**Runtime verified:** app alone rebuilt/restarted with data preserved;43 workspace/container source/config files match current source. App/simulator/UI healthHTTP200 and container six-tool MCP inventory/directory/status reads passed. One live security/P2 draft check passed with SP-001/KB-006 citations and no impact clarification. No approval or create_ticket sent; simulator/UI untouched. UI http://127.0.0.1:7860. [Evidence](evidence/repeated-lockout-2026-10-26/SUMMARY.md).

**Preserved results:** historical65/69, repeats22/23,22/23,21/23 (three S2-07 failures and one OWN-08 connection failure); later OWN-08 pass and supplemental503 initial1/1+repeated3/3 remain separate. Supplemental503 does not pass supplied S2-07. Final onboarding targeted63offline+one livePASS and the seven earlier user-reported manual passes remain scoped historical evidence. The new lockout manual PASS is recorded separately below. [Manual passes](evidence/final-verification-2026-10-26/manual-results.md).

**Completed portfolio work:** README screenshot, architecture/startup links, real/simulated table, category results, failure/fix narrative, acknowledgements and confirmed solo contributions are complete. set168111 performed project decisions, directed/reviewed AI-assisted implementation, manually tested and validated fixes; Codex/ChatGPT assisted design/code/debugging/documentation. Full name omitted. Peer checklist prepared, not performed.

**Still outstanding:** independent fresh-clone preflight; unverified registration/DESIGN review/check-ins and unresolved solo-versus-pair course requirement; separately authorized public product repo/clean publication review/tag/video/live demo/submission. No peer/trainer approval is claimed. Optional judge, cloud/Jira/A2A/production features and capstone optimisation are not mandatory mini-project work. The assignment does not prescribe100% supplied-case success or another full repeated run.

**S2-07:** official sample_requests.md explicitly expects hardware/P3, while the supplied input omits impact/workaround facts required by KB-015 and KB-010 has no default dock priority. Supplied case and clarification remain unchanged. [Exact conflict](evidence/supplemental-dock-2026-10-26/policy-conflict.md). Instructor clarification is unavailable, not the next required action.

**Historical lockout-verification budget snapshot:** confirmed$1.89905922, retained unknown$0.04033004, available$0.56061074. One authorized live chat cost$0.00583914; app alone rebuilt/restarted, no source edits in this verification phase. No approval/create_ticket, full-suite rerun, unrelated work, Git or release actions.

## Current design

Support chooses bounded reads/drafts; Reviewer checks grounding/completeness with one correction. Retrieval preserves20-document metadata, applies source/department precedence and uses real embeddings. Supplied MCP reaches directory/status/history and approval-only writes. SQLite retains issue context, requester facts and immutable action payloads.

The lockout correction is a deterministic policy boundary in the existing files, not a new agent or service. A possible password-guessing pattern is security/P2; it is not automatically an activeP1 incident. User facts must establish>=3 lockouts, daily timeframe and unknown cause. VIP, four affected users and existing active-security rules retainP1. It does not reuse Finance's no-troubleshooting exception or bypass requested-draft/attempt/approval requirements.

Source claims are bounded: this lexical recognizer and scripted offline checks do not establish exhaustive language or real-model reliability. No architecture expansion or new dependencies.



_Publication current-section extract; historical evidence retained._
