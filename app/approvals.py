"""Schema validation and approval-only immutable ticket commits; no model calls."""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator

from app.storage import Store, canonical

ROOT = Path(__file__).resolve().parent.parent
IMMEDIATE_ESCALATION = "No troubleshooting attempted; immediate escalation required by policy."


def response(session_id: str, reply: str, *, state: str = "answered", pending_action=None,
             result=None, tool_calls=None) -> dict:
    return {"session_id": session_id, "reply": reply, "state": state,
            "pending_action": pending_action, "result": result,
            "citations": [], "tool_calls": tool_calls or []}


def public_action(action: dict) -> dict:
    return {key: action[key] for key in ("action_id", "type", "summary", "payload")}


def matching_incident(status: dict, employee: dict, payload: dict) -> dict | None:
    text = payload["subject"] + " " + payload["description"]
    codes = set(re.findall(r"\b[A-Z]{2,6}-\d{2,4}\b", text.upper()))
    gateway = employee.get("vpn_gateway") or employee.get("gateway")
    for incident in status.get("incidents", []):
        if incident.get("status") != "active" or not codes.intersection(incident.get("error_codes", [])):
            continue
        if incident.get("service") == "vpn":
            if employee.get("department") == "Finance":
                continue
            affected_gateways = re.findall(r"\bGW-\d\b", incident.get("affected", "") + " " + incident.get("title", ""))
            if affected_gateways and (not gateway or gateway not in affected_gateways):
                continue
        return incident
    return None


class Approvals:
    def __init__(self, store: Store, mcp, policy_check=None, current_fingerprint=None):
        self.store, self.mcp = store, mcp
        self.policy_check = policy_check
        self.current_fingerprint = current_fingerprint
        self.schema = Draft202012Validator(json.loads((ROOT / "dataset/schemas/ticket.schema.json").read_text(encoding="utf-8")))
        manifest = json.loads((ROOT / "dataset/manifest.json").read_text(encoding="utf-8"))
        self.docs = {doc["id"]: doc for doc in manifest["documents"]}

    def validate(self, payload: dict, employee: dict):
        self.schema.validate(payload)
        if payload["requester_email"] != employee.get("email") or payload["department"] != employee.get("department"):
            raise ValueError("Draft requester and department must match the verified employee directory")
        if any(ref not in self.docs or self.docs[ref]["status"] != "current" for ref in payload["kb_refs"]):
            raise ValueError("Draft contains an unknown or noncurrent source")
        text = (payload["subject"] + " " + payload["description"]).lower()
        vpn = bool(re.search(r"\bvpn\b|nakhlaconnect|\bnx-\d", text))
        if employee.get("department") == "Contractors" and vpn:
            raise ValueError("Contractor VPN access cannot be escalated as a ticket")
        if employee.get("department") == "Finance" and vpn:
            if payload["category"] != "security" or payload["priority"] not in {"P1", "P2"}:
                raise ValueError("Finance remote access must route to Security Operations at P2 or higher")
        if employee.get("department") == "Executive Office" or employee.get("vip") or payload.get("affected_users", 1) >= 4:
            if payload["priority"] != "P1":
                raise ValueError("VIP and four-or-more-user tickets must be P1")
        if len(payload["description"]) > 4000:
            raise ValueError("Draft description too long")

    def propose(self, session_id: str, payload: dict, employee: dict, fingerprint: str = "") -> dict:
        payload = json.loads(canonical(payload))
        payload.setdefault("affected_users", 1)
        self.validate(payload, employee)
        # Canonical JSON covers every field. The UI additionally renders all payload fields.
        summary = "Create ticket with exactly these fields: " + canonical(payload)
        return public_action(self.store.propose(session_id, payload, summary, fingerprint))

    def retry(self, session_id: str, action_id: str) -> dict | None:
        action = self.store.reopen(session_id, action_id)
        return public_action(action) if action else None

    async def decide(self, session_id: str, action_id: str, approved: bool) -> dict:
        if type(approved) is not bool:
            return response(session_id, "Approval must be true or false.")
        if not approved:
            rejected = self.store.reject(session_id, action_id)
            return response(session_id, "Draft rejected. Nothing was written." if rejected else "This draft is unavailable or already used. Nothing was written.")
        status, action = self.store.claim(session_id, action_id)
        if status != "claimed":
            # Replays never send another write and don't pretend the current request created anything.
            return response(session_id, "This approval is unknown, expired, already used or still processing. No new write was sent.")
        payload = action["payload"]
        reconciling = action["status"] == "pending_recovery"
        write_started = False
        try:
            directory = await self.mcp.call("lookup_employee", {"email": payload["requester_email"]})
            status_result = await self.mcp.call("get_service_status", {})
            if not directory.get("ok") or not status_result.get("ok"):
                self.store.finish(action_id, "unknown" if reconciling else "failed", error={"code": "preflight_unavailable"})
                reply = ("Could not verify directory and live status. No new write was sent; the earlier write outcome remains unknown. Retry only this same action."
                         if reconciling else "Could not verify directory and live status. No ticket creation was sent. Ask to retry this exact draft.")
                return response(session_id, reply, tool_calls=self.mcp.drain_trace())
            employee = directory["employee"]
            self.validate(payload, employee)
            incident = matching_incident(status_result.get("status", {}), employee, payload)
            if incident:
                if reconciling:
                    self.store.finish(action_id, "unknown", error={"code": "active_incident_unreconciled"})
                    return response(session_id, f"Active incident {incident['id']} now matches this problem. No new write was sent; the earlier write outcome remains unknown. Follow the status page instructions and retry only this same draft and action key for reconciliation.", state="unknown", tool_calls=self.mcp.drain_trace())
                self.store.finish(action_id, "superseded", error={"code": "active_incident"})
                return response(session_id, f"Active incident {incident['id']} now matches this problem. No individual ticket was created. Follow the status page instructions.", tool_calls=self.mcp.drain_trace())
            if self.current_fingerprint and action["fingerprint"] != self.current_fingerprint():
                if reconciling:
                    raise ValueError("Unknown write requires reconciliation before changed evidence can be applied")
                self.store.finish(action_id, "superseded", error={"code": "changed_evidence"})
                return response(session_id, "The evidence changed. This draft needs a fresh review and approval; no write was sent.", tool_calls=self.mcp.drain_trace())
            if self.policy_check:
                issue = self.policy_check(payload, employee, status_result.get("status", {}))
                if inspect.isawaitable(issue):
                    issue = await issue
                if issue:
                    raise ValueError(str(issue))
            write_started = True
            result = await self.mcp.create_approved_ticket(payload, action_id)
            if result.get("ok"):
                ticket_id = result.get("ticket", {}).get("ticket_id")
                if not isinstance(ticket_id, str) or not re.fullmatch(r"IT-\d{4}", ticket_id):
                    self.store.finish(action_id, "unknown", error={"code": "invalid_write_result"})
                    return response(session_id, "The system response did not confirm a ticket identifier. The write outcome is unknown; retry only this same action.", tool_calls=self.mcp.drain_trace())
                confirmed = {"ticket_id": ticket_id}
                self.store.finish(action_id, "succeeded", result=confirmed)
                return response(session_id, f"Your ticket is {ticket_id}.", state="succeeded", result=confirmed, tool_calls=self.mcp.drain_trace())
            error = result.get("error") or {"code": "unknown"}
            unknown = reconciling or error.get("code") in {"timeout", "unreachable", "mcp_error", "invalid_tool_response", "unknown"} or error.get("http_status") == 504
            self.store.finish(action_id, "unknown" if unknown else "failed", error=error)
            if unknown:
                reply = "The ticket operation timed out or lost its connection. Its outcome is unknown; no success is confirmed. Ask to retry this same immutable draft and action key."
            elif error.get("http_status") in {409, 422}:
                self.store.finish(action_id, "invalid", error=error)
                reply = "The ticket was not created: the system rejected the draft. Correct the draft and obtain a new approval."
            else:
                reply = "Ticket creation failed or is unavailable. No ticket was confirmed. Ask to retry this exact draft."
            return response(session_id, reply, state="unknown" if unknown else "failed", tool_calls=self.mcp.drain_trace())
        except Exception:
            if write_started or reconciling:
                self.store.finish(action_id, "unknown", error={"code": "unconfirmed_write"})
                return response(session_id, "The write outcome is unknown. No ticket is confirmed; retry only this same draft and action key.", state="unknown", tool_calls=self.mcp.drain_trace())
            self.store.finish(action_id, "invalid", error={"code": "draft_revalidation_failed"})
            return response(session_id, "This draft no longer passes validation. No further write was sent; prepare a corrected draft for approval.", tool_calls=self.mcp.drain_trace())
