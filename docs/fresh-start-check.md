# Isolated fresh-start check - agent-run PASS

**27 October update:** [current-source Docker verification](../evidence/docker-approval-incident-2026-10-27/SUMMARY.md) passed with cached working data and focused mocked regressions. The isolated fresh-start described below remains historical; it was not rerun. Independent peer preflight is still uncompleted.

[Actual results, costs and evidence](../evidence/isolated-fresh-start-2026-10-26/SUMMARY.md). All 20 documents and cached restart passed; actual embedding cost $0.00022386, aggregate remaining $0.55457014. No chat, approval or ticket creation. Only isolated services stopped; working UI remains at http://127.0.0.1:7860.

Extra steps beyond the default README, required to keep an existing installation untouched:

1. Read the actual working ledger plus retained isolated ledger snapshots. Allocate at most $0.02 for fresh ingestion against the existing aggregate limit. Do not copy, delete or reset spending data. For this check the working ledger remained read only, and the retained isolated ledger is explicitly added to aggregate accounting.
2. Use a temporary standalone Compose configuration, distinct project and a fresh named data volume. Replace published mappings with loopback 7861:7860, 8001:8000 and 8104:8102. Keep internal service URLs unchanged. An additive ports override or project name alone is insufficient. Ensure all ports and the new volume name are unused.
3. Use absolute package build contexts, private process credentials instead of copying the working .env, matching private simulator/app keys and PROJECT_BUDGET_USD=0.02. Check effective configuration privately. Start/build only this project. These configuration adjustments were external to the unchanged packaged application/Compose file.
4. Wait for HTTP readiness, including the UI HTML and /config; Compose --wait only establishes running status for the UI. An immediate request disconnected during this check. Resume the same resources if needed; never start another fresh volume to bypass an ingestion reservation.
5. Read index metadata, health, stdio MCP inventory/directory/status and UI-to-app connectivity. Confirm 20 documents, two PDFs, 100 chunks and zero sessions/actions/created tickets. Restart only the isolated app and verify cached=true, identical vector hash and unchanged ledger rows.
6. Stop only isolated services, retain the named volume and sanitized evidence, and add actual charges/reservations to aggregate accounting. No down -v or data reset. The existing app must remain running unchanged.

Independent [peer preflight](peer-preflight.md) remains separate and uncompleted. This check did not run acceptance cases, publish or submit anything. A new independent preflight needs its own authorization and key/budget; this pass is not permission for more paid calls.
