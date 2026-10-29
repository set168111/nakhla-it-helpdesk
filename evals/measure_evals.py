"""Time the unchanged shared evaluator and retain honest per-case usage evidence.

Usage matches run_evals.py, except --judge is refused because its provider calls
are outside the application's shared budget ledger. This wrapper never changes
the shared evaluator's assertions, results, filtering or exit code.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import statistics
import sys
import time
from urllib.parse import urlsplit

try:
    from . import run_evals as runner
except ImportError:
    import run_evals as runner

ROOT = Path(__file__).resolve().parents[1]
USAGE_KEYS = ("prompt_tokens", "completion_tokens", "cost_usd", "confirmed_cost_usd",
              "calculated_cost_usd", "unknown_reserved_usd")


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        return None
    return value


def p95(values):
    return sorted(values)[math.ceil(.95 * len(values)) - 1] if values else None


class ObservedClient:
    """Transparent client proxy; only safe numeric usage from app turns retained."""
    def __init__(self, client):
        self.client = client
        self.turns = []

    def __getattr__(self, name):
        return getattr(self.client, name)

    def post(self, url, *args, **kwargs):
        start = time.perf_counter()
        path = urlsplit(str(url)).path
        monitored = path in {"/api/chat", "/api/approve", "/api/voice"}
        try:
            response = self.client.post(url, *args, **kwargs)
        except Exception:
            if monitored:
                self.turns.append({"path": path, "wall_seconds": time.perf_counter()-start,
                                   "usage_missing": True, "usage_unknown": True, "usage": {}, "cost_usd": None})
            raise
        if monitored:
            try:
                body = response.json()
            except ValueError:
                body = None
            usage = body.get("usage") if isinstance(body, dict) else None
            present = isinstance(usage, dict)
            safe = {key: _number(usage.get(key)) for key in USAGE_KEYS} if present else {}
            unknown = not present or safe.get("cost_usd") is None or bool(safe.get("unknown_reserved_usd"))
            self.turns.append({"path": path, "wall_seconds": time.perf_counter()-start,
                               "http_status": response.status_code, "usage_missing": not present,
                               "usage_unknown": unknown, "usage": safe,
                               "cost_usd": None if unknown else safe["cost_usd"]})
        return response


def ledger_snapshot():
    path = Path(os.getenv("APP_DATA_DIR", ROOT / "data")) / "spending.sqlite3"
    if not path.exists():
        return {"available": False}
    db = None
    try:
        db = sqlite3.connect(path.resolve().as_uri()+"?mode=ro", uri=True)
        values = db.execute("SELECT COALESCE(SUM(cost),0),COALESCE(SUM(CASE WHEN cost IS NULL THEN reserved ELSE 0 END),0),COALESCE(SUM(CASE WHEN actual=0 AND cost IS NOT NULL THEN cost ELSE 0 END),0),COUNT(*) FROM spending").fetchone()
        return {"available": True, "confirmed_cost_usd": values[0], "unknown_reserved_usd": values[1],
                "calculated_cost_usd": values[2], "reservations": values[3]}
    except sqlite3.Error:
        return {"available": False, "reason": "ledger_unreadable"}
    finally:
        if db is not None:
            db.close()


def metadata(cases_file: Path):
    files = [*sorted((ROOT / "app").glob("*.py")), ROOT / "requirements.txt",
             ROOT / "evals/run_evals.py", Path(cases_file)]
    hashes = {str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else path.name:
              hashlib.sha256(path.read_bytes()).hexdigest() for path in files if path.is_file()}
    corpus = hashlib.sha256()
    corpus_files = [ROOT / "dataset/manifest.json", *sorted((ROOT / "dataset/knowledge_base").glob("*"))]
    for path in corpus_files:
        if path.is_file():
            corpus.update(path.name.encode())
            corpus.update(path.read_bytes())
    config = {key: os.getenv(key, default) for key, default in {
        "MODEL": "openai/gpt-4.1-mini", "EMBEDDING_MODEL": "openai/text-embedding-3-small",
        "PROJECT_BUDGET_USD": "2.50", "HELPDESK_TODAY": "real-today"}.items()}
    return {"generated_utc": datetime.now(timezone.utc).isoformat(), "source_sha256": hashes,
            "corpus_sha256": corpus.hexdigest(), "safe_config": config,
            "safe_config_sha256": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()}


def summarise(rows):
    durations = [r["wall_seconds"] for r in rows]
    turns = [t for row in rows for t in row["turns"]]
    costs_complete = bool(rows) and all(row["cost_usd"] is not None for row in rows)
    total = sum(row["cost_usd"] for row in rows) if costs_complete else None
    return {"attempted_case_runs": len(rows), "passed_case_runs": sum(row["passed"] for row in rows),
            "success_rate": sum(row["passed"] for row in rows)/len(rows) if rows else None,
            "case_wall_avg_seconds": statistics.mean(durations) if durations else None,
            "case_wall_p95_seconds": p95(durations),
            "turn_wall_avg_seconds": statistics.mean([t["wall_seconds"] for t in turns]) if turns else None,
            "turn_wall_p95_seconds": p95([t["wall_seconds"] for t in turns]),
            "usage_complete": costs_complete, "total_cost_usd": total,
            "average_cost_per_attempted_case_usd": total/len(rows) if costs_complete else None,
            "turns_missing_usage": sum(t["usage_missing"] for t in turns),
            "turns_with_unknown_usage": sum(t["usage_unknown"] for t in turns),
            "confirmed_cost_reported_partial_usd": sum(t["usage"].get("confirmed_cost_usd") or (t["cost_usd"] or 0) for t in turns),
            "unknown_reserved_usd": sum(t["usage"].get("unknown_reserved_usd") or 0 for t in turns)}


def main():
    if "--judge" in sys.argv[1:]:
        raise SystemExit("--judge is not metered by the shared application ledger; measurement wrapper refuses paid judge calls.")
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--cases", type=Path, default=runner.HERE / "cases.sample.jsonl")
    ap.add_argument("--out", type=Path, default=runner.HERE / "scorecard.md")
    known, _ = ap.parse_known_args()
    runner.load_env()
    original = runner.run_case
    rows = []
    before = ledger_snapshot()

    def measured(case, urls, client, cases_file, judge, verbose):
        observed = ObservedClient(client)
        start = time.perf_counter()
        result = original(case, urls, observed, cases_file, judge, verbose)
        seconds = time.perf_counter()-start
        complete = len(observed.turns) == len(result.get("turns", [])) and bool(observed.turns) and all(t["cost_usd"] is not None for t in observed.turns)
        rows.append({"case_id": result["id"], "category": result["category"], "passed": result["passed"],
                     "wall_seconds": seconds, "cost_usd": sum(t["cost_usd"] for t in observed.turns) if complete else None,
                     "turns": observed.turns})
        return result

    runner.run_case = measured
    outcome = "interrupted_or_preflight_failed"
    try:
        exit_code = runner.main()
        outcome = "shared_runner_returned"
        return exit_code
    finally:
        runner.run_case = original
        report = {"scope": "Unmodified shared evaluator; whole-case time includes setup, all turns and assertions; turn timings are separate; no judge.",
                  "outcome": outcome, "metadata": metadata(known.cases.resolve()),
                  "ledger_before": before, "ledger_after": ledger_snapshot(),
                  "summary": summarise(rows), "cases": rows}
        path = known.out.with_suffix(".case-metrics.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Whole-case metrics written to {path}")


if __name__ == "__main__":
    sys.exit(main())
