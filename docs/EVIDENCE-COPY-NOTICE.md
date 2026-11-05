# Publication evidence copies and redactions

The package contains reviewed copies/extracts of preserved working-project evidence, not a new test run. Files with removed private paths or credentials have `.redacted` in their names; their original evidence stays unchanged in the working project. `docs/package-provenance.json` maps source paths/hashes to package paths/hashes and states transformations. Before publication the staged initial commit was scanned for credential patterns and private paths (counts only, recorded in package-verification.json); that is a static pattern check, not a legal clearance or an audit of any other history.

Current-section extracts of TASKS/HANDOVER/REQUIREMENTS/DESIGN and the publication-specific operations guide are labelled as extracts. Historical scores, original failed attempts, separate retests/supplemental503 and manual-versus-automated provenance are preserved; no test expectation or application file is altered. Package guidance pointers link to the official course snapshot instead of copying course Markdown, visuals or logos. The fictional KB-018 fixture is source data and is not redacted.

See [LICENSE.md](../LICENSE.md), [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) and [publication file list](publication-files.md).

## Excluded local history

Machine-specific native tooling, backup REQUIREMENTS.md, raw data/index/database/session backups and unrelated Capstone material stay local and are intentionally not packaged. Links routed here identify omitted private history, not replacement proof of a pass.

Historical evidence may retain earlier budgets, file counts and verification stages. Those values are snapshots, not current package claims; use package-verification.json and publication-files.txt for this assembled copy. The current exact count is in package-verification.json. No original score or later retest is silently substituted.

The isolated fresh-start evidence records a subsequent agent-run check, not an independent peer run. Its startup/interruption logs are reviewed copies with any private paths/credentials removed; raw local originals remain retained.


## Coordinated November submission update

The current source/setup/tests are copied from the reviewed working implementation.
New manual/status docs distinguish Case19 user-verified PASS from incomplete
Case20. The native stop helper now uses a portable root and the optional browser
test example uses a clone-relative interpreter; both transformations are recorded.
Current package verification/provenance supersede old file-count and source-parity
claims without replacing historical tests or observations. No real passwords,
password hashes, tokens, databases or private backups are package artifacts.

## Navigation polish scope

The new public summary reports the scoped 37 offline/65 isolated-browser checks
and all-layer/image activation verification. Raw live data, credential material,
private source/SQLite backups and machine-specific deployment evidence remain
local. No provider call or full acceptance rerun is inferred.
