"""Scoped incremental package refresh; no app imports, services or network."""
from pathlib import Path
import importlib.util
import json
import subprocess

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("assembly", ROOT / "evidence/publication-cleanup-2026-10-26/assemble_local_package.py")
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)
package = a.PACKAGE
prov_path = package / "docs/package-provenance.json"
prov = json.loads(prov_path.read_text())
entries = {item["original_local_path"]: item for item in prov["files"]}
changed = [".gitignore", "app/agent.py", "app/approvals.py", "tests/test_agent_workflow.py", "tests/test_approvals.py", "README.md", "HANDOVER.md", "TASKS.md", "docs/publication-files.md"]
changed += [p.relative_to(ROOT).as_posix() for p in (ROOT / "evidence/approval-incident-2026-10-26").iterdir() if p.is_file()]
for name in changed:
    src = ROOT / name
    raw = src.read_bytes()
    output = raw
    transformations = ["scoped approval-incident correction refresh"]
    redactions = 0
    if name in a.RECORDS:
        output = (a.read_text(src).partition("<details>")[0] + "\n_Publication current-section extract; historical records retained locally._\n").encode()
        transformations.append("current-section extract")
    if name.startswith("evidence/") or name in a.RECORDS or name.endswith(".md"):
        if src.suffix == ".json":
            data, redactions = a.scrub_json(json.loads(a.read_text(src)))
            output = json.dumps(data, indent=2).encode()
        else:
            text, redactions = a.scrub(a.read_text(src) if name.startswith("evidence/") else output.decode("utf-8"))
            output = text.encode()
    actual = str(Path(name).with_name(Path(name).stem + ".redacted" + Path(name).suffix)).replace("\\", "/") if redactions and name.startswith("evidence/") else name
    if name == "docs/publication-files.md":
        # Preserve package-specific curated explanation.
        output = (a.read_text(package / name).partition("\nCurrent-source refresh:")[0] + "\nCurrent-source refresh: [approval/incident evidence](../evidence/approval-incident-2026-10-26/SUMMARY.md). Docker/fresh-start verification predates these runtime changes.\n").encode()
        transformations.append("preserved package-specific manifest explanation plus refresh notice")
    entries[name] = {"original_local_path": name, "original_sha256": a.digest(raw), "package_path": actual, "transformations": transformations, "redactions": redactions}
    dest = package / actual
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(output)
mapping = {name: item["package_path"] for name, item in entries.items()}
for name in changed:
    if name.endswith(".md") and name != "docs/publication-files.md":
        dest = package / mapping[name]
        dest.write_text(a.rewrite_links(name, dest.read_text(), mapping, set(entries)), encoding="utf-8")
# Retain existing package-specific ignore safeguards.
p = package / ".gitignore"
p.write_text(p.read_text() + "\n# Local package safety\n.env.*\n!.env.example\nlocal-packages/\n/*.log\n**/pre-verification-data/\n**/pre-local-checkpoint-records/\n**/*browser-profile*/\n")
prov["files"] = list(entries.values())
prov["scope"] = "Reviewed publication copies; scoped offline approval-incident refresh; historical Docker/fresh-start predates changes"
prov["docker_verification_predates_runtime_changes"] = True
prov["source_application_unchanged"] = False
prov_path.write_text(json.dumps(prov, indent=2))
a.finish()
# Read-only git command still evaluates the nested package ignore rules.
r = subprocess.run(["git", "check-ignore", "--no-index", "-v", "--non-matching", "--", "local-packages/nakhla-it-helpdesk/services/data/employees.json", "local-packages/nakhla-it-helpdesk/services/data/status.json", "local-packages/nakhla-it-helpdesk/data/runtime-probe.txt"], cwd=ROOT, capture_output=True, text=True)
(ROOT / "evidence/approval-incident-2026-10-26/package-ignore.txt").write_text(r.stdout + r.stderr)
print(r.stdout)
