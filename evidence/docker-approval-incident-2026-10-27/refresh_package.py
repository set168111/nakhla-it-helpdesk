"""Scoped local package refresh for completed Docker runtime verification."""
from pathlib import Path
import importlib.util,json
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("assembly",ROOT/"evidence/publication-cleanup-2026-10-26/assemble_local_package.py")
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
package=a.PACKAGE;prov_path=package/"docs/package-provenance.json";prov=json.loads(prov_path.read_text());entries={x["original_local_path"]:x for x in prov["files"]}
changed=["README.md","TASKS.md","HANDOVER.md","DESIGN.md","REQUIREMENTS.md","docs/publication-files.md","docs/fresh-start-check.md"]
changed += [p.relative_to(ROOT).as_posix() for p in OUT.iterdir() if p.is_file() and p.name not in {"package-refresh-report.json","previous-package-verification.json"}]
changed += ["evidence/schema-copy-experiment-2026-10-27/"+n for n in ["SUMMARY.md","comparison.json","manual-quality-review.json","experiment-ledgers-after.json"]]
for name in changed:
 src=ROOT/name;raw=src.read_bytes();output=raw;redactions=0;trans=["current-source Docker evidence refresh; runtime source unchanged"]
 if name in a.RECORDS:
  output=(a.read_text(src).partition("<details>")[0]+"\n_Publication current-section extract; historical evidence retained._\n").encode();trans.append("current-section extract")
 if name.startswith("evidence/"):
  if src.suffix==".json":
   data,redactions=a.scrub_json(json.loads(a.read_text(src)));output=json.dumps(data,indent=2).encode()
  else:
   text,redactions=a.scrub(a.read_text(src));output=text.encode()
 elif name.endswith(".md"):
  text,redactions=a.scrub(output.decode());output=text.encode()
 if name=="docs/publication-files.md":
  old=a.read_text(package/name).partition("\nCurrent-source refresh:")[0]
  output=(old+"\nCurrent-source refresh: [27 October Docker verification](../evidence/docker-approval-incident-2026-10-27/SUMMARY.md) passed within its bounded scope. Historical isolated fresh-start and independent peer status remain separate.\n").encode();trans.append("preserved package-specific manifest explanation")
 actual=str(Path(name).with_name(Path(name).stem+".redacted"+Path(name).suffix)).replace("\\","/") if redactions and name.startswith("evidence/") else name
 entries[name]={"original_local_path":name,"original_sha256":a.digest(raw),"package_path":actual,"transformations":trans,"redactions":redactions}
 dest=package/actual;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(output)
mapping={n:i["package_path"] for n,i in entries.items()}
for name in changed:
 if name.endswith(".md") and name!="docs/publication-files.md":
  dest=package/mapping[name];dest.write_text(a.rewrite_links(name,dest.read_text(),mapping,set(entries)),encoding="utf-8")
prov["files"]=list(entries.values());prov["scope"]="Reviewed local publication copies; current-source Docker verification evidence added; no publication"
prov["docker_verification_predates_runtime_changes"]=False
prov["runtime_source_unchanged_by_current_verification"]=True
prov_path.write_text(json.dumps(prov,indent=2))
# Retain previous static report as new evidence; do not rewrite historical scores.
(OUT/"previous-package-verification.json").write_bytes((package/"docs/package-verification.json").read_bytes())
a.finish()
report_path=package/"docs/package-verification.json";report=json.loads(report_path.read_text());runtime=json.loads((OUT/"verification.json").read_text())
matches={n:a.digest((package/n).read_bytes())==h for n,h in runtime["source_sha256"].items()}
assert runtime["passed"] and all(matches.values()) and report["passed"]
report["docker_verification"]="PASS - current-source app rebuild, cached startup, health/MCP/UI and ten in-container mocked regressions; no paid calls"
report["current_container_source_matches"]=matches
report["historical_runtime_manifest_note"]="all_43_verified_runtime_file_hashes_match compares the older26October lockout manifest; current27October match is reported separately"
report["fresh_start"]="Historical isolated PASS predating approval/incident changes; not rerun; current-source working-data Docker verification separately passed"
report["runtime_evidence"]="evidence/docker-approval-incident-2026-10-27/verification.json"
report_path.write_text(json.dumps(report,indent=2));(a.AUDIT/"package-verification.json").write_text(json.dumps(report,indent=2));(OUT/"package-refresh-report.json").write_text(json.dumps(report,indent=2))
print(json.dumps({"package_passed":report["passed"],"files":report["file_count"],"current_container_files_matched":len(matches),"manifest_exact":report["manifest_exactly_matches_files"],"missing_links":report["missing_files_or_links"],"privacy_matches":report["private_path_matches_no_values"]}))
