# Isolated fresh-start verification - agent-run PASS

26 October 2026. This is an agent-run clean-package check, **not independent peer preflight**. No application source changed and no acceptance suite was repeated.

| Check | Actual result |
|---|---|
| Isolation | Separate Compose project `nakhla-helpdesk-preflight-20261026-cfc47b`, new named volume, loopback UI/app/simulator ports 7861/8001/8104 |
| Fresh real ingestion | All 20 documents, including both PDFs; 100 chunks, 100 x 1536 real OpenRouter vectors |
| Source identity | All 43 runtime/config files matched the packaged source |
| Readiness | App and simulator HTTP 200; UI HTML/config HTTP 200; UI container could reach app health |
| MCP | Six-tool inventory; successful lookup_employee and get_service_status reads only |
| Cached restart | Same vector hash/fingerprint and same single billing row; cached=true in logs |
| Writes | Zero chat/approval calls, zero sessions/actions, zero created tickets |
| Cleanup | Only isolated services stopped; volume retained for billing/evidence; working container identities/start times and ledger unchanged |

## Cost and aggregate budget

Working ledger before/after: confirmed $1.90487596, retained unknown reservations $0.04033004, 1617 rows. Fresh ingestion settled at **$0.00022386 actual**, within its $0.02 cap. No new unknown reservations. Aggregate confirmed **$1.90509982**, retained unknown **$0.04033004**, remaining **$0.55457014** of $2.50.

The working SQLite ledger was read only. Future budget decisions must sum it with the retained isolated ledger represented in [aggregate-ledger.json](aggregate-ledger.json); do not use the working-only remaining balance or count the stopped volume as a fresh budget. The isolated volume retains the original ledger. No spending limit was reset or bypassed.

## README steps and observed interruption

The README's default ports collide with the existing installation. For this specifically authorized parallel check, a temporary standalone Compose copy replaced published ports, used a distinct project and fresh named volume, supplied credentials through private process environment instead of copying .env, and set PROJECT_BUDGET_USD=0.02. Internal ports stayed unchanged. Effective Compose configuration was checked privately; no secrets/config values were published.

A verification-helper build-context type error occurred before any Docker startup or paid call. After correcting only that helper, fresh ingestion succeeded. Compose --wait does not establish UI readiness: the first immediate UI request disconnected. That interruption and conservative temporary $0.02 reservation are preserved in initial-attempt/. The same retained containers/volume were resumed, with bounded HTTP readiness retries; no new volume or ingestion charge was introduced. Both resumed startup and explicit app restart used the cached index. README now states to wait for UI readiness and explains parallel isolation.

## Evidence

[Results](results.json), [initial index/ledger/source hashes](initial-ingestion.json), [cached restart snapshot](after-cached-restart.json), [ingestion/restart log](app-ingestion-restart.log), [HTTP/UI](http-ui-checks.json), [UI-to-app](ui-to-app-check.json), [MCP](mcp-check.json), [aggregate before](aggregate-before.json), [aggregate after](aggregate-ledger.json), [Compose isolation plan](compose-plan.json), [running isolated containers](isolated-containers-running.json), [stopped isolated containers](isolated-containers-stopped.json), [working before](working-containers-before.json), [working after](working-containers-after.json), [initial interruption](initial-attempt/results.json).

Historical 65/69, three unresolved S2-07 attempts, OWN-08's separate passing retest, supplemental 503 initial 1/1 plus repeated 3/3 and user-reported manual passes remain separate. This check does not resolve S2-07 or confer peer/instructor approval. No Git, publication, recording or submission.
