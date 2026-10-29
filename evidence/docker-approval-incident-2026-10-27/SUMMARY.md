# Current-source Docker verification - 27 October 2026

**PASS within the stated scope.** Only the app image was rebuilt and app container recreated. Existing UI and simulator container IDs/images were retained and started. Working baseline remains in place; optimisation stopped and schema-removal candidate was not promoted.

## Verified

- All43 runtime/config files match the working source, both in a network-disabled/read-only image probe and the running app container. The baseline textual schema line is retained. [Manifest](runtime-source-manifest.json), [image/cache probe](image-cache-probe.json), [container source](container-source-check.json).
- Cached startup:20documents,100chunks; `cached=true`, no ingestion/provider calls. [Startup log](app-startup.log).
- App/simulator health200; UI HTML/config200 with20components; UI container reaches app health200. [HTTP/UI](http-ui-checks.json), [UI backend](ui-to-app-check.json), [container health](container-health-final.json).
- Actual MCP six-tool inventory, lookup_employee and get_service_status reads passed. No write tools invoked. [MCP](mcp-read-check.json).
- Unchanged UI and simulator source/config copies checked. [UI](ui-source-check.json), [simulator](simulator-source-check.json).
- **Ten focused existing regressions passed inside the app container**,0failures/errors/skips. They cover late-incident supersession/no-write; uncertain recovery and duplicate-write guards; concurrent/replayed approval safety; same immutable retry key; changed evidence; tampering; expiry; interrupted recovery; error-code retention through truncation; and gateway-scoped incident suppression. Test MCP/model calls are fake, test state is TemporaryDirectory per test, and the harness blocks networking. Fake write assertions are not real ticket writes. [Report](focused-container-tests.json), [log](focused-container-tests.log).
- Simulator audit has0created tickets and onlyGETrequests: no resets, approvals, notes or ticket writes. [Audit](simulator-read-only-audit.json).
- Working source, indexes, durable databases/ledgers and traces remain byte-identical; session/action counts remain494/159. Transient SQLite WAL/SHM files are separately identified. [Preservation](preservation-after.json).

## Budget and preserved history

No paid calls. Actual read-only ledger accounting remains aggregate confirmed$1.94088480, unknown reservations$0.04033004 and remaining**$0.51878516**. Includes the retained isolated-ingestion ledger and both private schema-experiment ledgers. [Accounting](aggregate-budget-after.json).

Historical65/69, unresolved S2-07, separate OWN-08/supplemental503, user-reported manual passes and earlier results are unchanged. The schema-removal experiment is completed but not adopted:7.10%fewer observed input tokens and5.96%lower observed cost, with quality wording/presentation concerns and six-turn measurement limitations. Its private baseline/candidate copies, ledgers and results remain retained. No further optimisation was performed.

## Scope limits and retained interruptions

This verifies current-source container startup/connectivity and focused mocked regressions. It is not fresh paid model acceptance, a full-suite rerun, an independent peer preflight or a new isolated fresh-start. The older isolated fresh-start proof still predates the approval/incident changes. Remaining gaps include independent peer preflight and the historical S2-07 policy/sample-case disagreement; no new score is substituted for historical evaluation.

Initial app-build output capture failed on Windows cp1252 decoding; a subsequent cached app-only build completed with UTF-8 capture. The first preservation comparison encountered a removed SQLite SHM file; durable-file comparison then passed without repair. Both interruptions are retained, not represented as product/test failures.

UI is running at **http://127.0.0.1:7860**. No runtime source edits, refactoring, further optimisation, Git, publication or release actions. Local clean-package refresh is separately recorded static work.
