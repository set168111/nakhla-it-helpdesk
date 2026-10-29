"""Verify intermediate draft assertions in a measured supplemental scorecard.

Usage: python evals/check_supplemental_result.py path/to/scorecard.json
No network or paid calls; supplied evaluator remains unchanged.
"""
import json
from pathlib import Path
import sys


def verify(path):
    report = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = report["results"]
    assert rows, "No supplemental results"
    for row in rows:
        assert row["passed"], row
        draft, approval = row["turns"]
        assert draft["result"] is None, "Write before approval"
        pending = draft["pending_action"]
        assert pending["type"] == "create_ticket"
        payload = pending["payload"]
        assert payload["category"] == "hardware", payload
        assert payload["priority"] == "P3", payload
        assert "I can continue working using the laptop screen." in payload["description"]
        assert approval["turn"] == {"approve": True}
        assert approval["result"] is None
        assert approval["pending_action"] is None
        checks = {check["check"]: check["ok"] for check in row["checks"]}
        assert checks["tools_used_include"]
        assert checks["state tickets"]
        assert checks["reply_contains_any"] and checks["reply_not_contains"]
    print(f"PASS: {len(rows)} supplemental P3/approval/create-failure/zero-ticket flow(s)")


if __name__ == "__main__":
    verify(sys.argv[1])
