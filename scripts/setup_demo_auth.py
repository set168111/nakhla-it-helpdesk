"""LOCAL DEMO ONLY: provision demo logins. Run from the project root with the project interpreter:

    .venv/Scripts/python.exe -B scripts/setup_demo_auth.py            # create accounts (once)
    .venv/Scripts/python.exe -B scripts/setup_demo_auth.py --rotate   # new random passwords for everyone
    .venv/Scripts/python.exe -B scripts/setup_demo_auth.py inspect-legacy   # read-only legacy report

Creates, never printing a password:
  data/auth.sqlite3                          salted scrypt hashes only (inside the data volume, outside the image)
  secrets/demo/demo-accounts.json            plaintext sheet read by the app for the demo-admin page (mounted read-only)
  secrets/eval/eval-credentials.json         separate credentials used by evals/run_evals.py (never mounted)
  secrets/private/demo-admin-credential.txt  the demo-admin password (never mounted)
secrets/ is git-ignored and Docker-ignored. Each employee has an individual random demo password and a
separate random eval password.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.auth import AuthService, legacy_action_report, legacy_session_ids  # noqa: E402

# The smallest set covering every evaluation case (evals/*.jsonl, 15 distinct employees) and every
# manual tracker case (sara, omar, rana, bashar, tariq are all inside it). The other 10 directory
# employees are not used by any case and get no login.
DEMO_EMAILS = [
    "bashar.tannous", "dalia.awwad", "fadi.mansour", "karim.saba", "lama.jaber", "mona.shaheen", "nadia.issa",
    "noor.barakat", "omar.farah", "rami.odeh", "rana.khalil", "salma.aziz", "sara.mikhail", "tariq.hamdan",
    "ziad.hourani",
]
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"   # no look-alike characters


def new_password() -> str:
    return "-".join("".join(secrets.choice(ALPHABET) for _ in range(5)) for _ in range(4))   # ~114 bits


def write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def restrict_to_current_user(directory: Path) -> None:
    """Best effort on Windows (chmod does nothing there): only the current user may read the directory.
    Applied to eval/ and private/, which are never mounted into a container."""
    if os.name != "nt" or not directory.exists():
        return
    import subprocess
    user = os.environ.get("USERNAME")
    if user:
        subprocess.run(["icacls", str(directory), "/inheritance:r", "/grant:r", f"{user}:(OI)(CI)F"],
                       capture_output=True, check=False)


def provision(args) -> int:
    secrets_dir, data_dir = Path(args.secrets_dir), Path(args.data_dir)
    sheet, evals = secrets_dir / "demo" / "demo-accounts.json", secrets_dir / "eval" / "eval-credentials.json"
    admin_file = secrets_dir / "private" / "demo-admin-credential.txt"
    auth = AuthService(data_dir / "auth.sqlite3")
    if auth.employee_count() and sheet.exists() and evals.exists() and admin_file.exists() and not args.rotate:
        restrict_to_current_user(secrets_dir / "eval")
        restrict_to_current_user(secrets_dir / "private")
        print(f"already provisioned ({auth.employee_count()} accounts); use --rotate to issue new passwords")
        return 0
    directory = {e["email"]: e for e in json.loads(Path(args.employees).read_text(encoding="utf-8"))["employees"]}
    wanted = [name + "@nakhla.example" for name in DEMO_EMAILS]
    missing = [email for email in wanted if email not in directory]
    if missing:
        print("not in the directory: " + ", ".join(missing), file=sys.stderr)
        return 1
    accounts, eval_accounts = [], {}
    for email in wanted:
        employee = directory[email]
        demo_password, eval_password = new_password(), new_password()
        auth.provision_employee(employee["employee_id"], email, employee["name"], employee["department"])
        auth.set_password(employee["employee_id"], "demo", demo_password)
        auth.set_password(employee["employee_id"], "eval", eval_password)
        accounts.append({"email": email, "name": employee["name"], "department": employee["department"], "password": demo_password})
        eval_accounts[email] = eval_password
    admin_password = new_password()
    auth.set_admin_password(admin_password)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    write_private(sheet, json.dumps({"note": "LOCAL DEMO ONLY", "generated": stamp, "accounts": accounts}, indent=1))
    write_private(evals, json.dumps({"note": "LOCAL EVAL ONLY", "generated": stamp, "accounts": eval_accounts}, indent=1))
    write_private(admin_file, "LOCAL DEMO ONLY - demo admin password for http://localhost:8000/demo/login\n" + admin_password + "\n")
    write_private(secrets_dir / "README.txt", "Generated by scripts/setup_demo_auth.py. Git-ignored and Docker-ignored.\n"
                  "demo/ is mounted read-only into the app container; eval/ and private/ never are.\n")
    restrict_to_current_user(secrets_dir / "eval")
    restrict_to_current_user(secrets_dir / "private")
    print(f"provisioned {len(accounts)} employee logins (demo + eval passwords each) and the demo admin")
    print(f"  password hashes : {data_dir / 'auth.sqlite3'}")
    print(f"  demo sheet      : {sheet}")
    print(f"  eval credentials: {evals}")
    print(f"  demo admin      : {admin_file}")
    return 0


def inspect_legacy(args) -> int:
    helpdesk = Path(args.data_dir) / "helpdesk.sqlite3"
    ids = legacy_session_ids(helpdesk)
    report = legacy_action_report(helpdesk) if helpdesk.exists() else {}
    report["legacy_sessions_to_retire"] = len(ids)
    print(json.dumps(report, indent=1))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", nargs="?", default="provision", choices=["provision", "inspect-legacy"])
    parser.add_argument("--data-dir", default=str(ROOT / "data"))
    parser.add_argument("--secrets-dir", default=str(ROOT / "secrets"))
    parser.add_argument("--employees", default=str(ROOT / "services" / "data" / "employees.json"))
    parser.add_argument("--rotate", action="store_true", help="issue new random passwords for every account")
    args = parser.parse_args()
    return provision(args) if args.command == "provision" else inspect_legacy(args)


if __name__ == "__main__":
    sys.exit(main())
