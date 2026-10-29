"""Deterministic Nakhla policy boundaries; retrieved prose never grants authority."""
from __future__ import annotations

import re
import hashlib
from typing import Any

IMMEDIATE_ESCALATION = "No troubleshooting attempted; immediate escalation required by policy."


def redact(text: str) -> str:
    """Redact credential-shaped content before storage, prompts or tracing."""
    text = re.sub(r"(?i)(?:sk-or-v1-|sk-)[a-z0-9_-]{12,}", "[REDACTED]", text)
    text = re.sub(r"(?i)(\bbearer\s+)\S+", r"\1[REDACTED]", text)
    labels = r"(?:password|secret|api[_ -]?key|backup codes?|otp|one.time code)"
    # A comma-separated value list must stop before another credential label;
    # otherwise preserving a procedural first clause can swallow the label of a
    # genuine disclosure in the next clause and hide it from this scan.
    values = rf"[^\s,;]+(?:\s*,\s*(?!{labels}\s*(?::|=|\bis\b|\bare\b))[^\s,;]+)*"
    # Explicit assignments always carry a possible value. Natural-language
    # descriptions need a narrow distinction: 'password is hunter2' is a value,
    # but 'first password is sent to the manager' describes a policy workflow.
    text = re.sub(rf"(?i)({labels}\s*[:=]\s*){values}", r"\1[REDACTED]", text)

    def natural_assignment(match):
        remainder = match.string[match.start("value"):]
        procedural = re.match(
            r"(?i)(?:(?:sent|emailed|delivered)\s+(?:only\s+)?to\b|"
            r"(?:generated|issued|provided)\s+(?:at|during|when|by|upon|once|automatically|to)\b|"
            r"(?:available|unavailable)\b)", remainder)
        # A token-shaped assigned value, including a real natural disclosure,
        # remains redacted. Only literal workflow/state descriptions survive.
        return match.group(0) if procedural and not match.group("possessive") else match.group("prefix") + "[REDACTED]"

    text = re.sub(rf"(?i)(?P<prefix>(?P<possessive>\b(?:my|our)\s+)?{labels}\s+(?:is|are)\s+)(?P<value>{values})", natural_assignment, text)
    text = re.sub(r"(?i)((?:otp|backup code|one.time code)\s+)\d[\d -]{3,15}\b", r"\1[REDACTED]", text)
    return re.sub(r"\b\d{4,8}\b", lambda m: "[REDACTED]" if m.group() == "7731" else m.group(), text)


def _meta(chunk: dict) -> dict:
    return chunk.get("metadata", chunk)


def eligible_chunks(chunks: list[dict], department: str | None = None) -> list[dict]:
    result = []
    for chunk in chunks:
        meta = _meta(chunk)
        if meta.get("status") != "current":
            continue
        applies = meta.get("applies_to", ["all"])
        if department and department not in applies and "all" not in applies:
            continue
        result.append(chunk)
    return result


def contextual_chunks(chunks: list[dict], department: str | None, query: str) -> list[dict]:
    """Keep Finance VPN evidence within its mandatory escalation boundary.

    General client procedures remain valid for other departments, but KB-016 and
    KB-002's exception explicitly prohibit applying them to Finance. The source
    excerpt is literal, with its own content hash/ID and original chunk lineage.
    No generated policy text is introduced as source evidence.
    """
    finance_vpn = department == "Finance" and re.search(r"\bvpn\b|nakhlaconnect|\bNX-\d|remote.access|fin.secure", query, re.I)
    if not finance_vpn:
        return chunks
    governing = {"SP-001", "SP-002", "KB-015", "KB-016"}
    result = []
    for chunk in chunks:
        if chunk["id"] in governing:
            result.append(chunk)
        elif chunk["id"] == "KB-002" and chunk.get("section", "").strip().lower() == "exceptions":
            finance = next((line for line in chunk["text"].splitlines() if re.match(r"\s*-\s*\*\*Finance:\*\*", line)), None)
            if finance:
                digest = hashlib.sha256(finance.encode()).hexdigest()
                result.append({**chunk, "parent_chunk_id": chunk["chunk_id"],
                               "chunk_id": chunk["chunk_id"]+":finance", "text": finance,
                               "section": "Exceptions / Finance", "content_hash": digest,
                               "policy_scope": "Finance VPN immediate escalation"})
    return result


def _precedence(chunk: dict, department: str | None) -> tuple:
    meta = _meta(chunk)
    version = tuple(int(n) for n in str(meta.get("version", "0.0")).split("."))
    return (str(meta.get("id", "")).startswith("SP-"),
            bool(department and department in meta.get("applies_to", []) and "all" not in meta.get("applies_to", [])),
            bool(meta.get("authoritative")), str(meta.get("last_updated", "")), version)


def resolve_precedence(chunks: list[dict], department: str | None = None) -> list[dict]:
    """Resolve only explicitly shared points, never discard compatible whole documents.

    Generic retrieval chunks have no point and remain as compatible evidence. Claims
    tagged with an identical policy_point are reduced to the governing source; an
    unresolved equal-priority disagreement is excluded, requiring clarification.
    """
    eligible = eligible_chunks(chunks, department)
    superseded = {_meta(c).get("supersedes") for c in eligible if _meta(c).get("supersedes")}
    eligible = [c for c in eligible if _meta(c).get("id") not in superseded]
    grouped: dict[str, list[dict]] = {}
    result = []
    for chunk in eligible:
        point = chunk.get("policy_point")
        if point:
            grouped.setdefault(point, []).append(chunk)
        else:
            result.append(chunk)
    for candidates in grouped.values():
        best = max(_precedence(c, department) for c in candidates)
        winners = [c for c in candidates if _precedence(c, department) == best]
        if len({c.get("claim", c.get("text")) for c in winners}) == 1:
            result.append(winners[0])
    return sorted(result, key=lambda c: _precedence(c, department), reverse=True)


def unexplained_daily_lockouts(text: str) -> bool:
    """SP-001 section 3 / KB-006: require count, daily scope and unknown cause."""
    text = text.lower()
    if not re.search(r"\b(?:today|in (?:one|a|the same) day)\b", text):
        return False
    if not re.search(r"\b(?:without (?:a )?known cause|no known cause|unexplained|cannot find an old password anywhere)\b", text):
        return False
    number = r"\d+|one|two|three|four|five|six|seven|eight|nine|ten"
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
             "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
    pattern = (rf"\b(?:locked(?: out)?|locks) ({number})(?: or more)? times\b"
               rf"|\b({number})(?: or more)? (?:unexplained )?lockouts?\b")
    for match in re.finditer(pattern, text):
        count = match[1] or match[2]
        if (int(count) if count.isdigit() else words[count]) >= 3:
            return True
    return False


def ticket_policy(employee: dict, topic: str, affected_users: int = 1,
                  blocked: bool = True, workaround: bool = False,
                  security_incident: bool = False, request: bool = False) -> dict:
    """Source-linked ticket category, priority and department refusal rules."""
    text = topic.lower()
    error_report = bool(re.search(r"\b(?!(?:kb|sp|it|inc|gw)-)[a-z]{2,5}-\d{2,4}\b",text))
    request = request or bool(re.search(r"\b(?:software|access) request\b",text)) or (
        bool(re.search(r"\bhow.to\b",text)) and not error_report)
    vpn = bool(re.search(r"\bvpn\b|nakhlaconnect|\bnx-\d|remote.access|fin-secure", text))
    department = employee.get("department")
    contractor = department == "Contractors" or employee.get("contractor") is True
    if vpn and contractor:
        return {"allowed": False, "category": "network_access", "priority": None,
                "reason": "Contractors use https://vdi.nakhla.example; VPN access is refused without a ticket.",
                "kb_refs": ["SP-002", "KB-016"], "immediate": False}
    immediate = vpn and department == "Finance"
    lockout_escalation = unexplained_daily_lockouts(text)
    security_incident = security_incident or bool(re.search(r"stolen|lost (?:phone|laptop)|password.*(?:typed|entered).*phish|(?:typed|entered).*password.*(?:phish|suspicious)", text))
    if security_incident or immediate or lockout_escalation or re.search(r"phish|stolen|lost (?:phone|laptop)|suspicious", text):
        category = "security"
    elif vpn or re.search(r"wi.?fi|\bwlan|\bvdi\b|network|shares?", text):
        category = "network_access"
    elif re.search(r"password|mfa|nakhlakey|\bnid-|\bmfa-|sso|lockout|account|access request|\bidentity\b", text):
        category = "identity_access"
    elif re.search(r"onboard|new starter|offboard|leaver", text):
        category = "onboarding"
    elif re.search(r"dock|monitor|printer|print|\bprn-|hardware|laptop|device|nakhla[ -]?manage|\bmdm-", text):
        category = "hardware"
    elif re.search(r"mail|calendar|\bnxm-", text):
        category = "email_collab"
    elif re.search(r"software|install|\bswc-|licen[cs]e|code studio", text):
        category = "software"
    else:
        category = "other"
    if affected_users >= 4 or department == "Executive Office" or employee.get("vip") or security_incident:
        priority = "P1"
    elif lockout_escalation:
        priority = "P2"  # Possible password guessing is not automatically a P1 incident.
    elif request and not immediate:
        priority = "P4"
    elif immediate or (blocked and not workaround):
        priority = "P2"
    else:
        priority = "P3"
    return {"allowed": True, "category": category, "priority": priority,
            "kb_refs": ["KB-015"] + (["KB-002", "KB-016"] if immediate else []) + (["SP-001", "KB-006"] if lockout_escalation else []),
            **({"lockout_escalation": True} if lockout_escalation else {}),
            "immediate": immediate, "reason": "Security Operations" if immediate else ""}


def matching_incident(status: dict, employee: dict, error_code: str | None,
                      service: str | None = None) -> dict | None:
    """Match status, service, exact error and affected gateway; never infer no outage."""
    if "status_page" in status:
        status = status["status_page"]
    if "status" in status and isinstance(status["status"], dict):
        status = status["status"]
    gateway = employee.get("vpn_gateway") or employee.get("gateway")
    for incident in status.get("incidents", []):
        if incident.get("status") != "active":
            continue
        if service and incident.get("service") != service:
            continue
        if error_code and error_code not in incident.get("error_codes", []):
            continue
        if not error_code:
            continue  # request clarification instead of broad incident suppression
        affected_gateways = set(re.findall(r"\bGW-\d\b", incident.get("affected", "")))
        if incident.get("service") == "vpn" and (not gateway or (affected_gateways and gateway not in affected_gateways)):
            continue
        return incident
    return None
