# Historical readiness review and current submission update

The review below predates this coordinated update. Source/docs synchronization
and package checks are now prepared; see [submission status](submission-status.md).
Case19 wording is USER-VERIFIED PASS; Case20 remains incomplete/code deferred.
No fresh-clone runtime, instructor agreement or submission is inferred.

<details><summary>Earlier review observations, retained as history</summary>

# Submission readiness review - 2026-11-05

Documentation and read-only local inspection only. No snippet rerun, tests, paid
calls, application edits, service operations, credentials provisioning, Git writes,
commits, pushes or remote fetch. Tracker/checkpoint updates do not imply acceptance.
Historical 65/69, original failures and separate manual passes remain unchanged.

## Latest snippet observation

USER-REPORTED: **SAFE BUT UNHELPFUL; relevant clarification INCOMPLETE**.
Do not repeat this test. This is not a useful-clarification pass or a new security
certification. Do not infer SQL execution from SQL text or a model response.

Existing stored evidence read-only:
- Fresh `' OR '1'='1 --` session hash bd00bbdeb76a, trace
  c16a442f6f204ac18f193d1d94917a4b: continue/support, selected_read=clarify,
  one model call. Existing generic troubleshooting question does not establish
  the requested snippet/task clarification.
- Existing software-context SELECT session hash 6b411b0ab6ad, final trace
  d59ea74a04044256b08f5338b68ab7cf: continue/support, retrieve, draft candidate,
  one bounded revision, Reviewer accepted=false/complete=false twice. The
  recorded checks reject irrelevant SQL in the description and missing/contextual
  requirements; finalise's recorded rejected-review path renders the safe unverified
  stop. SQL remains in the stored cumulative issue; no successful relevant
  clarification is established. Exact input-to-trace pairing is inferred from
  session/sequence; process-local HMAC is unavailable.
- Zero action rows in both matching sessions. Candidate drafting in a trace is not
  a saved pending draft or a created ticket. User-reported safety is retained with
  these bounded observations; there was no live replay.

Case18 theft-refusal passes and Case19 core-flow pass remain separate. Case19
intake wording repair is last recorded ACTIVE, but no new manual wording pass is
claimed from this review. Existing pending drafts must not be exercised or changed.

## Remaining tasks, priority order

1. **Reconcile grading access and private instructor setup.** Mandatory login is a
   deliberate API-contract change: unauthenticated hidden tests get 401; a typed
   email is not identity. Obtain instructor agreement on credential-aware grading
   before claiming compatibility. Prepare a private setup/handoff: instructor-owned
   .env/API key and explicitly authorized budget, locally generated demo/eval/admin
   credentials, exact login URLs and access instructions. The source generator is
   scripts/setup_demo_auth.py and must be packaged/run once before initial Compose
   startup. Do not rotate existing owner credentials, export the owner's auth DB,
   or put any generated passwords/tokens/keys in Git, images, README or video.
   Separate demo-admin password lives in secrets/private/demo-admin-credential.txt;
   employee sheet is secrets/demo/demo-accounts.json; eval credentials are separate
   under secrets/eval. No instructor-specific private handoff has been verified.

2. **Correct submission-facing startup/admin/demo documentation.** Working README
   runs Docker before telling users to provision auth, still advertises simulator
   health/ports on host 8102 and carries contradictory October latest-status/budget
   statements. docs/local-demo-login.md has stale pre-auth/not-activated/restore.ps1
   instructions; promote the latest checkpoint's preservation-safe status and label
   obsolete blocks historical. docs/peer-preflight.md omits auth setup and still
   claims no repo exists. docs/demo.md, docs/video-script.md and demo-commands.txt
   reference /admin/tickets, change-requester UI, asserted identity and host 8102
   reset/fault commands. Replace current-facing guidance with employee sign-in/out,
   http://127.0.0.1:8000/demo/login and /demo/tickets, loopback UI7860/app8000,
   and simulator internal-only by default. Any fault/eval override must be explicitly
   isolated/opt-in and preservation-safe; no reset of this running demo. Account
   setup prerequisites must be reproducible, without embedding private credentials.
   Update stale submission-status statements in README/HANDOVER/TASKS/publication
   notes and package instructions while preserving dated evidence. The completed
   portfolio video exists; do not invent a need to re-record it or a new test pass.

3. **Refresh curated publication contents and clean package.** Local publication
   clone: the separate publication checkout, local HEAD e8e7eb7 (Finalise portfolio
   video and refresh publication metadata). No local tags were listed. No remote
   fetch occurred; current remote visibility/HEAD are unverified. Normalized text
   comparisons (CRLF ignored) find 35 missing and 13 changed selected
   implementation/test/config paths in that clone; the local clean package has
   35 missing/13 changed paths in the same inventory. Publication README
   still describes asserted identity/no authentication. Missing production modules:
   app/auth.py, app/demo_admin.py. Missing required setup/eval support includes
   scripts/setup_demo_auth.py, auth_probe.py and docker-compose.eval.yml.
   Changed implementation includes app/agent.py, app/helpdesk_policy.py, app/main.py,
   ui/app_ui.py and evals/run_evals.py. Synchronize the relevant auth/ownership,
   admin/UI, startup preservation, narration, routing and Case8/19 regressions,
   templates/ignore rules/Compose, and reviewed sanitized evidence/docs. Do not
   blindly copy machine-specific scripts, private paths, full runtime traces,
   database backups, secrets or local-only deployment artifacts. Regenerate
   inclusion/provenance/source hashes, link checks and credential/privacy scans.
   This review did not edit the publication repository or package.

4. **Complete useful clarification and remaining manual scope.** The latest snippet
   result is safe but unhelpful; relevant clarification is incomplete. Any corrective
   implementation is a separately authorized task; do not rerun the snippet now.
   Case19 wording retest remains unverified unless an explicit user result supplies
   it. Preserve the recorded core-flow pass; no repeat of already passed flows or
   Approve/Reject operation on retained drafts is requested. Explain these limits
   honestly if submitting before further authorized work.

5. **Validate the final deliverable and baseline scope.** Current local deployment
   checks passed at the last activation; they do not validate a refreshed package
   or the older publication clone. After synchronization, run scoped offline/static
   packaging/source/privacy/link checks and an isolated authenticated fresh-clone
   startup/preflight. Independent peer preflight remains unperformed. The older
   October fresh-start is not a current-auth package pass. Record final-source
   evaluation coverage separately from historical 65/69: the auth-aware runner
   and S2-02 sign-in/string-check behavior changed; do not claim unchanged hidden-
   test compatibility or turn mocks into a paid/live baseline. Decide with the
   instructor whether additional authenticated baseline checks are needed; paid
   work requires separate budget approval. No blanket 69-case rerun is required
   by this review. Retain S2-07 policy/sample gap, OWN-08 original failure/separate
   retest, skipped checks and old spending reservations.

6. **Finish authorized delivery/course confirmations.** Verify instructor/reviewer
   repository access and required public visibility (last local publication record
   says private; no fresh online verification). Freeze/tag v1.0 only after approved
   contents/checks, confirm live-demo/Q&A and submission issue, and locate existing
   registration/DESIGN-review/check-in evidence or disclose it unverified. Resolve
   the disclosed solo-versus-pair requirement with the instructor. Repo/video already
   exist; do not list their creation as outstanding. No peer/instructor approval or
   course submission is established by local evidence.

## Publication comparison detail (selected source inventory)

Missing paths (not an instruction to publish all of them):

- app/auth.py
- app/demo_admin.py
- tests/auth_helpers.py
- tests/test_admin_all_tickets.py
- tests/test_auth_http.py
- tests/test_auth_hygiene.py
- tests/test_auth_queue_expiry.py
- tests/test_auth_service.py
- tests/test_batch2_integration.py
- tests/test_batch3_injection_http.py
- tests/test_batch3_perf_integration.py
- tests/test_batch4_session_races.py
- tests/test_batch5_functional_fixes.py
- tests/test_batch7_unsafe_draft_diagnostics.py
- tests/test_batch8_case8_corrections.py
- tests/test_case19_request_continuity.py
- tests/test_current_message_routing.py
- tests/test_database_input_safety.py
- tests/test_demo_admin.py
- tests/test_eval_runner_auth.py
- tests/test_identity_session_security.py
- tests/test_lockout_narration_conditions.py
- tests/test_login_ticket_continuity.py
- tests/test_startup_preservation.py
- tests/test_ui_enhancements.py
- tests/ui_fixtures.py
- tests/browser/serve_isolated_app.py
- tests/browser/ui_enhancements_smoke.py
- tests/browser/ui_smoke.py
- scripts/auth_probe.py
- scripts/Dockerfile.layer
- scripts/maintain_history.py
- scripts/setup_demo_auth.py
- scripts/stop-local.ps1
- docker-compose.eval.yml

Changed paths:

- app/agent.py
- app/helpdesk_policy.py
- app/main.py
- ui/app_ui.py
- evals/run_evals.py
- tests/test_agent_workflow.py
- tests/test_contract_safety.py
- README.md
- DESIGN.md
- docker-compose.yml
- .env.example
- .gitignore
- .dockerignore

</details>
