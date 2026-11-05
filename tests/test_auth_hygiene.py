"""OFFLINE secret-handling and workflow tests for the local demo login.

- scripts/setup_demo_auth.py: random individual passwords, hashes only in the database, nothing printed.
- Account selection covers every evaluation case and manual tracker employee.
- Repository / Docker hygiene: ignore rules, compose mounts, no real secret inside files that are
  git-tracked candidates or copied into an image (checked against the REAL generated secrets when present).
- End to end through HTTP: responses, traces, stores never contain a password or a login token, and the
  Case 8 flow (old-ticket lookup -> software request -> manager -> attempted step -> P4 draft -> Approve) works for a
  signed-in employee.

Run: python -B -m unittest tests.test_auth_hygiene -v
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from argparse import Namespace
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from app.auth import AuthService
from app.main import create_app
from tests.test_batch8_case8_corrections import M3, MESSAGES, TRUTHFUL, Case8Flow, PH
from tests.test_batch7_unsafe_draft_diagnostics import M1, M2, OMAR, TICKET_REF

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("setup_demo_auth", ROOT / "scripts" / "setup_demo_auth.py")
setup_demo_auth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup_demo_auth)


def run_setup(tmp: Path, *, rotate: bool = False) -> tuple[int, str]:
    args = Namespace(data_dir=str(tmp / "data"), secrets_dir=str(tmp / "secrets"), rotate=rotate,
                     employees=str(ROOT / "services" / "data" / "employees.json"))
    out, err = io.StringIO(), io.StringIO()
    # These tests exercise provisioning, not Windows ACLs. Granting only USERNAME
    # removes the sandbox identity's access to its own temporary test files.
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
            patch.object(setup_demo_auth, "restrict_to_current_user"):
        code = setup_demo_auth.provision(args)
    return code, out.getvalue() + err.getvalue()


class ProvisioningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.code, self.output = run_setup(self.root)
        self.sheet = json.loads((self.root / "secrets/demo/demo-accounts.json").read_text())
        self.evals = json.loads((self.root / "secrets/eval/eval-credentials.json").read_text())["accounts"]
        self.admin = (self.root / "secrets/private/demo-admin-credential.txt").read_text().splitlines()[1]

    def passwords(self):
        return [a["password"] for a in self.sheet["accounts"]] + list(self.evals.values()) + [self.admin]

    def test_creates_one_login_per_selected_employee_and_prints_no_password(self):
        self.assertEqual(self.code, 0)
        self.assertEqual(len(self.sheet["accounts"]), 15)
        self.assertEqual(sorted(self.evals), sorted(a["email"] for a in self.sheet["accounts"]))
        for password in self.passwords():
            self.assertNotIn(password, self.output)
        self.assertIn("provisioned 15 employee logins", self.output)

    def test_every_password_is_individual_random_and_strong(self):
        passwords = self.passwords()
        self.assertEqual(len(passwords), len(set(passwords)))                       # 15 demo + 15 eval + admin, all distinct
        for password in passwords:
            self.assertRegex(password, r"^[A-Za-z0-9]{5}(-[A-Za-z0-9]{5}){3}$")
            self.assertNotRegex(password, r"[0Oo1lI]")                              # no look-alike characters
        self.assertNotIn(self.admin.lower(), {"admin", "admin/admin", "password"})

    def test_database_holds_only_hashes_and_logins_work_for_the_right_account_only(self):
        blob = (self.root / "data/auth.sqlite3").read_bytes()
        for password in self.passwords():
            self.assertNotIn(password.encode(), blob)
        auth = AuthService(self.root / "data/auth.sqlite3")
        first, second = self.sheet["accounts"][:2]
        self.assertIsNotNone(auth.login(first["email"], first["password"]))
        self.assertIsNotNone(auth.login(first["email"], self.evals[first["email"]]))          # the separate eval credential
        self.assertIsNone(auth.login(first["email"], second["password"]))                     # not another employee password
        self.assertIsNone(auth.login(first["email"], self.admin))
        self.assertIsNotNone(auth.admin_login(self.admin))
        self.assertIsNone(auth.admin_login(first["password"]))

    def test_stable_internal_identities_come_from_the_directory(self):
        auth = AuthService(self.root / "data/auth.sqlite3")
        principal = auth.login("sara.mikhail@nakhla.example", next(a["password"] for a in self.sheet["accounts"] if a["email"].startswith("sara")))[2]
        directory = {e["email"]: e for e in json.loads((ROOT / "services/data/employees.json").read_text())["employees"]}
        self.assertEqual(principal.employee_id, directory[principal.email]["employee_id"])

    def test_rerun_keeps_credentials_and_rotate_replaces_them(self):
        before = (self.root / "secrets/demo/demo-accounts.json").read_bytes()
        code, output = run_setup(self.root)
        self.assertIn("already provisioned", output)
        self.assertEqual((self.root / "secrets/demo/demo-accounts.json").read_bytes(), before)
        old = self.sheet["accounts"][0]
        run_setup(self.root, rotate=True)
        auth = AuthService(self.root / "data/auth.sqlite3")
        self.assertIsNone(auth.login(old["email"], old["password"]))                           # old password no longer works
        fresh = json.loads((self.root / "secrets/demo/demo-accounts.json").read_text())["accounts"][0]
        self.assertIsNotNone(auth.login(fresh["email"], fresh["password"]))

    def test_demo_admin_secret_is_stored_apart_from_the_sheet_and_eval_file(self):
        self.assertNotIn(self.admin, (self.root / "secrets/demo/demo-accounts.json").read_text())
        self.assertNotIn(self.admin, (self.root / "secrets/eval/eval-credentials.json").read_text())
        for password in self.evals.values():
            self.assertNotIn(password, (self.root / "secrets/demo/demo-accounts.json").read_text())


class AccountSelectionTests(unittest.TestCase):
    def test_selected_accounts_cover_every_eval_case_and_manual_tracker_employee(self):
        selected = {name + "@nakhla.example" for name in setup_demo_auth.DEMO_EMAILS}
        used = set()
        for path in (ROOT / "evals").glob("*.jsonl"):
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    case = json.loads(line)
                    for source in [case] + case["turns"]:
                        if source.get("user"):
                            used.add(source["user"]["email"])
        self.assertTrue(used)                                                             # the cases do name employees
        self.assertLessEqual(used, selected)
        tracker = (ROOT / "docs" / "manual-security-test-tracker.md").read_text(encoding="utf-8")
        named = {m for m in re.findall(r"[a-z]+\.[a-z]+@nakhla\.example", tracker)}
        self.assertLessEqual(named, selected)
        directory = {e["email"] for e in json.loads((ROOT / "services/data/employees.json").read_text())["employees"]}
        self.assertLessEqual(selected, directory)
        self.assertLess(len(selected), len(directory))                                    # smallest covering set, not all 25
        self.assertEqual(selected, used | named)                                          # nobody extra: the smallest covering set


class RepositoryAndImageHygieneTests(unittest.TestCase):
    def test_ignore_rules_cover_every_secret_location(self):
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").split()
        self.assertIn("/secrets/", gitignore)
        self.assertIn("*.sqlite3", gitignore)
        self.assertIn("/data/", gitignore)
        for entry in ("secrets", "data", "*.sqlite3*", ".env"):
            self.assertIn(entry, dockerignore)
        if shutil.which("git"):
            for path in ("secrets/demo/demo-accounts.json", "secrets/eval/eval-credentials.json",
                         "secrets/private/demo-admin-credential.txt", "data/auth.sqlite3"):
                result = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT)
                self.assertEqual(result.returncode, 0, path + " is not git-ignored")

    def test_the_image_only_copies_source_directories(self):
        copies = re.findall(r"^COPY\s+(\S+)", (ROOT / "Dockerfile").read_text(encoding="utf-8"), re.M)
        self.assertEqual(sorted(copies), ["app", "dataset", "requirements.txt", "services", "ui"])

    def test_compose_mounts_only_the_demo_sheet_and_two_assets_and_publishes_least(self):
        compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))["services"]
        volumes = compose["app"]["volumes"]
        self.assertIn("./secrets/demo:/workspace/secrets/demo:ro", volumes)
        for volume in volumes:
            if "secrets" in volume:
                self.assertEqual(volume, "./secrets/demo:/workspace/secrets/demo:ro")       # never eval/ or private/
            if "demo-assets" in volume:
                self.assertTrue(volume.endswith(":ro"))
        self.assertNotIn("volumes", compose["ui"])
        self.assertNotIn("volumes", compose["helpdesk-api"])
        self.assertNotIn("ports", compose["helpdesk-api"])                                  # simulator not published to the host
        self.assertEqual(compose["app"]["ports"], ["127.0.0.1:8000:8000"])                  # direct API: loopback only
        override = yaml.safe_load((ROOT / "docker-compose.eval.yml").read_text(encoding="utf-8"))["services"]
        self.assertEqual(override["helpdesk-api"]["ports"], ["127.0.0.1:8102:8102"])

    def test_no_real_generated_secret_appears_in_files_that_git_or_an_image_could_carry(self):
        secrets_dir = ROOT / "secrets"
        if not (secrets_dir / "demo" / "demo-accounts.json").exists():
            self.skipTest("no real credentials generated yet")
        real = [a["password"] for a in json.loads((secrets_dir / "demo/demo-accounts.json").read_text())["accounts"]]
        try:
            real += list(json.loads((secrets_dir / "eval/eval-credentials.json").read_text())["accounts"].values())
            real.append((secrets_dir / "private/demo-admin-credential.txt").read_text().splitlines()[1])
        except PermissionError:
            self.skipTest("real eval/admin credentials are protected by Windows ACLs; full real-secret scan unavailable")
        skipped = {".venv", "secrets", "data", ".git", "__pycache__", "local-packages"}
        offenders = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or skipped & set(path.relative_to(ROOT).parts) or path.stat().st_size > 5_000_000:
                continue
            if path.suffix.lower() in {".mp4", ".png", ".jpg", ".npz", ".sqlite3", ".pdf", ".zip"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if any(password in text for password in real):
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [])
        for rel in ("data/traces.jsonl",):                                                  # runtime trace of the live app
            target = ROOT / rel
            if target.exists():
                text = target.read_text(encoding="utf-8", errors="ignore")
                self.assertFalse(any(password in text for password in real), rel)


class SignedInCase8EndToEndTests(Case8Flow):
    """Case 8 through the real HTTP contract with a signed-in employee, then secret-leak scans."""

    PASSWORD = "omar-end-to-end-password-Q7"

    def test_old_ticket_to_approved_p4_ticket_and_no_secret_in_any_output(self):
        auth = AuthService(self.data / "auth.sqlite3")
        auth.provision_employee("E-1005", OMAR["email"], "Omar Farah", "Sales")
        auth.set_password("E-1005", "demo", self.PASSWORD)
        workflow = self.workflow(*self.script())
        app = create_app(workflow, auth=auth)
        with TestClient(app) as client:
            login = client.post("/api/login", json={"email": OMAR["email"], "password": self.PASSWORD})
            token = login.json()["token"]
            headers = {"Authorization": "Bearer " + token}
            replies = [client.post("/api/chat", headers=headers, json={"session_id": "e2e-case8", "message": m}).json()
                       for m in MESSAGES]
            states = [r["state"] for r in replies]
            self.assertEqual(states, ["history", "clarification", "clarification", "await_confirmation"])
            self.assertEqual(self.mcp.writes, [])                                         # nothing before Approve
            pending = replies[-1]["pending_action"]
            self.assertEqual((pending["payload"]["category"], pending["payload"]["priority"]), ("software", "P4"))
            self.assertIn(PH, pending["payload"]["description"])
            self.assertNotIn(TICKET_REF, pending["payload"]["description"])
            approve = {"session_id": "e2e-case8", "action_id": pending["action_id"], "approved": True}
            done = client.post("/api/approve", headers=headers, json=approve).json()
            replay = client.post("/api/approve", headers=headers, json=approve).json()
            client.post("/api/logout", headers=headers)
            after_logout = client.post("/api/approve", headers=headers, json=approve)
        self.assertEqual(done["result"], {"ticket_id": "IT-2001"})
        self.assertIsNone(replay["result"])
        self.assertEqual(len(self.mcp.writes), 1)
        self.assertEqual(after_logout.status_code, 401)
        # No password or login token in any response, trace, conversation store or stored action.
        surfaces = [json.dumps(replies), json.dumps(done), json.dumps(replay), login.text.replace(token, "<token>"),
                    (self.data / "traces.jsonl").read_text(encoding="utf-8"),
                    json.dumps(self.store.get_session("e2e-case8")), json.dumps(self.store.latest_action("e2e-case8"))]
        for surface in surfaces:
            self.assertNotIn(self.PASSWORD, surface)
            self.assertNotIn(token, surface)
        self.assertNotIn(self.PASSWORD.encode(), (self.data / "auth.sqlite3").read_bytes())
        self.assertNotIn(token.encode(), (self.data / "auth.sqlite3").read_bytes())      # only the token hash is stored


class LegacyMigrationOnBackupCopyTests(unittest.TestCase):
    """The activation step, rehearsed on a TEMPORARY COPY of the real SQLite-API backup (never the live file)."""

    BACKUP = Path(__import__("os").environ.get("LEGACY_DB_BACKUP",
                  Path.home() / "helpdesk-rollback" / "auth-batch-2026-11-04" / "sqlite" / "helpdesk.sqlite3.backup"))

    def test_startup_retirement_on_a_copy_of_the_real_database(self):
        if not self.BACKUP.exists():
            self.skipTest("no rollback backup available at " + str(self.BACKUP))
        from app.auth import legacy_action_report, legacy_session_ids
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "helpdesk.sqlite3"
            shutil.copyfile(self.BACKUP, copy)
            before = copy.read_bytes()
            ids = legacy_session_ids(copy)
            self.assertGreater(len(ids), 0)
            auth = AuthService(Path(tmp) / "auth.sqlite3")
            auth.provision_employee("E-1", "sara.mikhail@nakhla.example", "Sara", "Support")
            self.assertEqual(auth.retire_legacy_sessions(ids), len(ids))
            self.assertEqual(auth.retire_legacy_sessions(ids), 0)                         # idempotent on every restart
            for session_id in ids[:5]:
                self.assertFalse(auth.claim_session(session_id, "E-1"))                   # never adopted
            self.assertEqual(copy.read_bytes(), before)                                    # the conversation data is untouched
            report = legacy_action_report(copy)
            self.assertEqual(report["needs_reconciliation"], [])                           # no unknown / committing / recovery writes


if __name__ == "__main__":
    unittest.main()
