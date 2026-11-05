"""OFFLINE workflow invariants: scripted model outputs and fake MCP/retrieval.

No provider is called and no embeddings are manufactured. These tests exercise
the production LangGraph, policy, persistence and approval coordinator, but do
not prove model quality or the real retrieval/provider integration.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
import time
import httpx
from openai import APITimeoutError
from unittest.mock import patch

from app.agent import SupportWorkflow, conversation_recall, draft_signal, requested_draft, sms_permission_question, claim_capacity, source_attempts, explicitly_nothing_tried, report_policy, onboarding_timing_error
from app.approvals import Approvals, IMMEDIATE_ESCALATION
from app.storage import Store


EMPLOYEE = {"email": "sara.mikhail@nakhla.example", "department": "Support", "vpn_gateway": "GW-1"}
CHUNK = {"chunk_id": "KB-006:test", "id": "KB-006", "title": "NakhlaID account lockout",
         "section": "Unlock", "metadata": {"status": "current", "error_codes": ["NID-423"]},
         "text": "Wait 30 minutes or use https://id.nakhla.example/unlock."}
VPN_CHUNK = {"chunk_id": "KB-002:test", "id": "KB-002", "title": "VPN error codes",
             "section": "Error codes", "metadata": {"status": "current", "error_codes": ["NX-403", "NX-503", "NX-781"]},
             "text": "NX-781 requires client 5.4 or later. Finance VPN problems go to Security Operations."}
ANSWER = {"intent": "answer", "claims": [{"text": "Wait 30 minutes.", "chunk_ids": [CHUNK["chunk_id"]]}]}


class FakeMCP:
    def __init__(self):
        self.employee = copy.deepcopy(EMPLOYEE)
        self.trace, self.calls, self.writes = [], [], []
        self.status = {"incidents": []}
        self.status_ok = True
        self.write_result = {"ok": True, "ticket": {"ticket_id": "IT-2001"}}
        self.tickets = []

    async def call(self, name, args):
        self.calls.append((name, copy.deepcopy(args)))
        self.trace.append({"tool": name, "ok": name != "get_service_status" or self.status_ok, "ms": 1})
        if name == "get_service_status":
            return {"ok": self.status_ok, "status": copy.deepcopy(self.status)}
        if name == "lookup_employee":
            return {"ok": True, "employee": copy.deepcopy(self.employee)}
        if name == "search_tickets":
            return {"ok": True, "tickets": copy.deepcopy(self.tickets), "count": len(self.tickets)}
        if name == "get_ticket":
            ticket=next((t for t in self.tickets if t['ticket_id']==args['ticket_id']),None)
            return {"ok":True,"ticket":copy.deepcopy(ticket)} if ticket else {"ok":False,"error":{"code":"ticket_not_found"}}
        raise AssertionError("Unexpected fake MCP read")

    async def create_approved_ticket(self, payload, action_id):
        self.writes.append((copy.deepcopy(payload), action_id))
        self.trace.append({"tool": "create_ticket", "ok": self.write_result["ok"], "ms": 1})
        return copy.deepcopy(self.write_result)

    def drain_trace(self):
        trace, self.trace = self.trace, []
        return trace


class FakeRetrieval:
    ready = True
    fingerprint = "offline-test-fingerprint"

    def __init__(self):
        self.chunks, self.queries = [copy.deepcopy(CHUNK), copy.deepcopy(VPN_CHUNK)], []

    async def search(self, query, department=None):
        self.queries.append((query, department))
        return copy.deepcopy(self.chunks)


class ScriptedWorkflow(SupportWorkflow):
    def __init__(self, *args, script=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.client = object()  # readiness sentinel only; _model below never calls it
        self.script = list(copy.deepcopy(script))
        self.script_calls = []

    async def _model(self, state, role, instruction, packet, schema):
        self.script_calls.append((role, schema.__name__, copy.deepcopy(packet)))
        state["model_calls"] += 1
        state["trace"].append({"role": role, "offline_scripted": True})
        if not self.script:
            raise AssertionError("Unexpected additional model invocation")
        return schema.model_validate(self.script.pop(0))


class TimeoutWorkflow(ScriptedWorkflow):
    """Test-only transport faults; no provider, reservation or real sleep."""
    failure_schema = "Decision"
    failures = 1
    short_deadline = False

    async def _model(self, state, role, instruction, packet, schema):
        if not hasattr(self,"attempts"):
            self.attempts = {}
        name = schema.__name__
        self.attempts[name] = self.attempts.get(name,0)+1
        if name == self.failure_schema and self.attempts[name] <= self.failures:
            state["model_calls"] += 1
            if self.short_deadline:
                state["deadline"] = time.monotonic()+10
            raise APITimeoutError(request=httpx.Request("POST","https://provider.invalid/test"))
        return await super()._model(state,role,instruction,packet,schema)


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    def test_unexplained_daily_lockouts_use_documented_security_priority(self):
        issue = "My NakhlaID account locked three times today without a known cause."
        policy, count = report_policy(EMPLOYEE, issue)
        self.assertEqual((policy["category"], policy["priority"], count), ("security", "P2", 1))
        self.assertNotIn("impact_missing", policy)
        self.assertEqual(report_policy(EMPLOYEE, issue + " I can still work using a workaround.")[0]["priority"], "P2")
        for employee, extra in [({**EMPLOYEE, "department": "Executive Office"}, ""),
                                (EMPLOYEE, " Four users are affected."),
                                (EMPLOYEE, " I entered my password into a phishing page.")]:
            self.assertEqual(report_policy(employee, issue + extra)[0]["priority"], "P1")
        for text in ["My account locked twice today without a known cause.",
                     "My account locked three times last month without a known cause.",
                     "My account locked three times today because my phone uses an old password.",
                     "My account locked three times today.",
                     "Five failed sign-ins today without a known cause."]:
            with self.subTest(text=text):
                self.assertNotEqual(report_policy(EMPLOYEE, text)[0]["category"], "security")
        for text in ["I had 3 unexplained lockouts in one day.",
                     "My account locked out four times today; I cannot find an old password anywhere."]:
            with self.subTest(text=text):
                self.assertEqual(report_policy(EMPLOYEE, text)[0]["priority"], "P2")

    async def test_repeated_lockout_followup_preserves_context_and_approval(self):
        await self.chat(self.workflow(*self.answer_script()), "My NakhlaID shows NID-423.")
        source = (Path(__file__).resolve().parents[1]/"dataset/knowledge_base/KB-006-account-lockout.md").read_text(encoding="utf-8")
        self.retrieval.chunks = [{**copy.deepcopy(CHUNK), "text": source}]
        followup = "My account locked three times today without a known cause. I already checked saved passwords and found none. Please open a ticket."
        draft = {"intent": "draft", "subject": "Repeated NID-423 lockouts", "description": followup,
                 "attempted_steps": ["I already checked saved passwords and found none."], "affected_users": 1,
                 "claims": [{"text": "Three unexplained daily lockouts require Security Operations escalation at P2.", "chunk_ids": [CHUNK["chunk_id"]]}]}
        def drafting():
            return self.workflow({"action": "retrieve"}, draft, {"accepted": True, "complete": True})
        result = await drafting().chat("s", followup, {"email": self.mcp.employee["email"]})
        self.assertEqual(result["state"], "await_confirmation")
        first = result["pending_action"]
        payload = first["payload"]
        self.assertEqual((payload["category"], payload["priority"]), ("security", "P2"))
        self.assertEqual(payload["requester_email"], EMPLOYEE["email"])
        self.assertEqual(payload["department"], EMPLOYEE["department"])
        self.assertIn("NID-423", payload["description"])
        self.assertEqual(payload["attempted_steps"], draft["attempted_steps"])
        self.assertIn("KB-006", payload["kb_refs"])
        self.assertEqual(self.mcp.writes, [])
        await self.approvals.decide("s", first["action_id"], False)
        self.assertEqual(self.mcp.writes, [])
        second = (await drafting().chat("s", "Please prepare a fresh ticket draft.", {"email": self.mcp.employee["email"]}))["pending_action"]
        self.assertNotEqual(second["action_id"], first["action_id"])
        await self.approvals.decide("s", first["action_id"], True)
        self.assertEqual(self.mcp.writes, [])
        approved = await self.approvals.decide("s", second["action_id"], True)
        self.assertEqual(approved["result"], {"ticket_id": "IT-2001"})
        await self.approvals.decide("s", second["action_id"], True)
        self.assertEqual(len(self.mcp.writes), 1)

    def test_documented_incident_priorities_preserve_unknown_impact(self):
        self.assertEqual(report_policy(EMPLOYEE, "Software Center SWC-2001 when I install the IDE. Open a ticket.")[0]["priority"], "P3")
        self.assertEqual(report_policy(EMPLOYEE, "VPN NX-112 still fails after Sync and restart. I cannot work.")[0]["priority"], "P2")
        self.assertEqual(report_policy(EMPLOYEE, "VPN NX-112. I cannot work but have a workaround.")[0]["priority"], "P3")
        self.assertIsNone(report_policy(EMPLOYEE, "Dock does not detect monitors after firmware update, cable replacement and restart.")[0]["priority"])
        self.assertEqual(report_policy(EMPLOYEE, "Dock does not detect monitors. I can continue working using the laptop screen.")[0]["priority"], "P3")
        self.assertIsNone(report_policy(EMPLOYEE, "CRM-1150. I am completely blocked.")[0]["priority"])
        self.assertEqual(report_policy({**EMPLOYEE, "department": "Executive Office"}, "SWC-2001")[0]["priority"], "P1")
        self.assertTrue(onboarding_timing_error("Submit the form 5 business days before to ensure timely preparation, including laptop availability."))

    def test_onboarding_timing_and_guarantee_guard(self):
        self.assertTrue(onboarding_timing_error("On the new starter's first day, the laptop is collected locally at the IT Service Desk counter for onsite starters, or delivered by courier the business day before for remote starters."))
        self.assertFalse(onboarding_timing_error("On the new starter's first day, collect the laptop locally. Remote starters receive it by courier the business day before."))
        self.assertTrue(onboarding_timing_error("On day 1, remote starters receive their laptop by courier the business day before their start date."))
        self.assertTrue(onboarding_timing_error("Submit the form 5 business days before to ensure laptop availability on day 1."))
        self.assertTrue(onboarding_timing_error("Late requests cannot guarantee a laptop on day 1, but timely forms ensure a laptop on day 1."))
        self.assertFalse(onboarding_timing_error("Local starters collect their laptop on day 1. Remote starters receive it by courier the business day before the start date."))
        self.assertFalse(onboarding_timing_error("Later requests cannot guarantee a laptop on day 1."))
        self.assertFalse(onboarding_timing_error("Remote leavers receive a courier label. Return the laptop within 5 business days."))

    async def test_onboarding_timing_correction_preserves_checklist_and_sources(self):
        import pymupdf
        with pymupdf.open(Path(__file__).resolve().parents[1]/"dataset/knowledge_base/KB-012-onboarding-offboarding.pdf") as pdf:
            source="\n".join(page.get_text() for page in pdf)
        self.assertIn("Remote starters receive it by courier the business day before.",source)
        self.assertIn("Collect the laptop at the IT Service Desk counter",source)
        chunk={"chunk_id":"KB-012:offline","id":"KB-012","title":"Onboarding and offboarding: IT checklist",
               "section":"Onboarding","metadata":{"status":"current","error_codes":[]},"text":source}
        self.retrieval.chunks=[chunk]
        before="The hiring manager submits the New Starter form through HR at least 5 business days before the start date with department, office and role. IT creates NakhlaID 3 business days before the start date. The first-password activation link goes to the hiring manager, never the starter's personal address. Later requests cannot guarantee a laptop on day 1."
        after="On day 1, open the activation link with your manager, set the password, enrol NakhlaKey, store 10 backup codes offline, and check Compliant in NakhlaManage. Request role access through access.nakhla.example; VPN-Users is automatic for employees, never contractors."
        bad={"intent":"answer","claims":[{"text":before+" On day 1, remote starters receive their laptop by courier the business day before their start date.","chunk_ids":[chunk["chunk_id"]]},
                                          {"text":after,"chunk_ids":[chunk["chunk_id"]]}]}
        fixed={"claims":[{"text":before,"chunk_ids":[chunk["chunk_id"]]},
                         {"text":"Local starters collect their laptop at the IT Service Desk counter on day 1. Remote starters receive it by courier the business day before their start date. "+after,"chunk_ids":[chunk["chunk_id"]]}]}
        workflow=self.workflow({"action":"retrieve"},bad,fixed,{"accepted":True,"complete":True})
        result=await self.chat(workflow,"What should a new employee do before their first day, and when will they receive their laptop?")
        self.assertEqual(result["state"],"answer")
        revision_packet = next(packet for _, schema, packet in workflow.script_calls if schema == "ClaimsRevision")
        self.assertIn("never combine 'first day'", revision_packet["review"]["corrections"])
        self.assertIn("Remote starters receive it by courier the business day before the start date.", revision_packet["review"]["corrections"])
        for fact in ["5 business days","3 business days","hiring manager","day 1","business day before","NakhlaKey","10 backup codes","Compliant","access.nakhla.example","never contractors"]:
            self.assertIn(fact,result["reply"])
        self.assertNotIn("On day 1, remote",result["reply"])
        self.assertEqual([c["id"] for c in result["citations"]],["KB-012"])
        self.assertEqual([schema for _,schema,_ in workflow.script_calls],["Decision","Candidate","ClaimsRevision","Review"])
        self.assertTrue(workflow.script_calls[2][2]["onboarding_checklist"])
        self.assertEqual(workflow.script_calls[2][2]["claim_capacity"],2)
        self.assertIsNone(workflow.script_calls[-1][2]["previous_review"])
        self.assertIsNone(result["pending_action"])
        self.assertEqual(self.mcp.writes,[])

    async def test_onboarding_repeated_timing_error_stops_without_publishing_it(self):
        chunk={"chunk_id":"KB-012:offline","id":"KB-012","title":"Onboarding","section":"Day 1",
               "metadata":{"status":"current","error_codes":[]},"text":"Local collection day 1. Remote courier delivery the business day before."}
        self.retrieval.chunks=[chunk]
        claim={"text":"On day 1, remote starters receive the laptop by courier the business day before.","chunk_ids":[chunk["chunk_id"]]}
        workflow=self.workflow({"action":"retrieve"},{"intent":"answer","claims":[claim]},{"claims":[claim]})
        result=await self.chat(workflow,"When does a remote new starter receive the laptop?")
        self.assertEqual(result["state"],"unverified")
        self.assertNotIn(claim["text"],result["reply"])
        self.assertEqual([schema for _,schema,_ in workflow.script_calls],["Decision","Candidate","ClaimsRevision"])

    async def test_onboarding_full_checklist_restores_missing_steps_without_changing_timing(self):
        text="Local starters collect the laptop on day 1. Remote starters receive it by courier the business day before their start date."
        steps="Open the activation link with your manager. Enrol NakhlaKey, store backup codes offline, check Compliant in NakhlaManage and request role access at access.nakhla.example."
        chunk={"chunk_id":"KB-012:offline","id":"KB-012","title":"Onboarding","section":"Checklist",
               "metadata":{"status":"current","error_codes":[]},"text":text+" "+steps}
        self.retrieval.chunks=[chunk]
        bad={"intent":"answer","claims":[{"text":text,"chunk_ids":[chunk["chunk_id"]]}]}
        fixed={"claims":[{"text":text,"chunk_ids":[chunk["chunk_id"]]},
                         {"text":steps,"chunk_ids":[chunk["chunk_id"]]}]}
        workflow=self.workflow({"action":"retrieve"},bad,fixed,{"accepted":True,"complete":True})
        result=await self.chat(workflow,"What should a new employee do before their first day, and when will they receive their laptop?")
        self.assertEqual(result["state"],"answer")
        self.assertIn("NakhlaKey",result["reply"])
        self.assertIn("NakhlaManage",result["reply"])
        self.assertIn("business day before",result["reply"])
        self.assertEqual([schema for _,schema,_ in workflow.script_calls],["Decision","Candidate","ClaimsRevision","Review"])

    def test_impact_policy_requires_evidence_and_handles_negation_and_updates(self):
        self.assertIsNone(report_policy(EMPLOYEE,"CRM-1150. Please prepare a ticket.")[0]["priority"])
        self.assertEqual(report_policy(EMPLOYEE,"This blocks me completely from working, and I have no workaround.")[0]["priority"],"P2")
        self.assertEqual(report_policy(EMPLOYEE,"Completely blocked, but I have a documented workaround.")[0]["priority"],"P3")
        self.assertEqual(report_policy(EMPLOYEE,"I have a documented workaround. This blocks me completely from working, and I have no workaround.")[0]["priority"],"P2")
        self.assertEqual(report_policy(EMPLOYEE,"Completely blocked, no workaround. I can still work using a documented workaround.")[0]["priority"],"P3")
        self.assertEqual(report_policy(EMPLOYEE,"I can still work; the service is degraded but usable.")[0]["priority"],"P3")
        self.assertEqual(report_policy({**EMPLOYEE,"department":"Executive Office"},"CRM-1150")[0]["priority"],"P1")
        self.assertEqual(report_policy({**EMPLOYEE,"department":"Finance"},"VPN NX-403")[0]["priority"],"P2")
        self.assertEqual(report_policy(EMPLOYEE,"I have a workaround. I cannot work; the workaround no longer works.")[0]["priority"],"P2")
        self.assertEqual(report_policy(EMPLOYEE,"I have a workaround. I cannot work; I no longer have a workaround.")[0]["priority"],"P2")
        self.assertEqual(report_policy(EMPLOYEE,"Completely blocked with no workaround. I am no longer completely blocked.")[0]["priority"],"P3")
        self.assertEqual(report_policy(EMPLOYEE,"How to fix CRM-1150? Please prepare a ticket. This blocks me completely from working, and I have no workaround.")[0]["priority"],"P2")
        self.assertEqual(report_policy(EMPLOYEE,"Software request for Inkscape.")[0]["priority"],"P4")
        self.assertEqual(report_policy(EMPLOYEE,"How to change my signature?")[0]["priority"],"P4")

    async def test_impact_update_replaces_pending_action_and_preserves_approved_payload(self):
        self.mcp.employee={"email":"omar.farah@nakhla.example","department":"Sales","vpn_gateway":"GW-2"}
        crm="The NakhlaCRM mobile app shows CRM-1150 when syncing contacts. How do I fix it?"
        first=await self.chat(self.workflow({"action":"retrieve"}),crm)
        self.assertEqual(first["state"],"unknown")
        workflow=self.workflow()
        missing=await workflow.chat("s","I haven't tried anything yet. Please prepare a ticket.",{"email":self.mcp.employee["email"]})
        self.assertEqual(missing["state"],"clarification")
        self.assertIn("workaround",missing["reply"])
        self.assertNotIn("error code",missing["reply"])
        self.assertIsNone(missing["pending_action"])
        self.assertEqual(workflow.script_calls,[])
        draft={"intent":"draft","subject":"CRM-1150 contact-sync error","description":crm,"attempted_steps":[],"affected_users":1}
        def drafting():
            return self.workflow({"action":"retrieve"},draft,{"accepted":True,"complete":True})
        first=await drafting().chat("s","I have a documented workaround: I can sync contacts using the web client.", {"email": self.mcp.employee["email"]})
        old=first["pending_action"]
        self.assertEqual(old["payload"]["priority"],"P3")
        original=copy.deepcopy(self.store.get_action(old["action_id"]))
        updated=await drafting().chat("s","This blocks me completely from working, and I have no workaround.", {"email": self.mcp.employee["email"]})
        new=updated["pending_action"]
        self.assertEqual(new["payload"]["priority"],"P2")
        self.assertNotEqual(new["action_id"],old["action_id"])
        self.assertIn("no workaround",new["payload"]["description"])
        self.assertEqual(self.store.get_action(old["action_id"])["status"],"superseded")
        self.assertEqual(self.store.get_action(old["action_id"])["payload"],original["payload"])
        self.assertEqual(self.store.get_action(old["action_id"])["payload_hash"],original["payload_hash"])
        stale=await self.approvals.decide("s",old["action_id"],True)
        self.assertFalse(stale.get("result"))
        self.assertEqual(self.mcp.writes,[])
        accepted=await self.approvals.decide("s",new["action_id"],True)
        self.assertTrue(accepted.get("result"))
        committed=copy.deepcopy(self.store.get_action(new["action_id"]))
        revised=await drafting().chat("s","I can still work using a documented workaround.", {"email": self.mcp.employee["email"]})
        self.assertEqual(revised["pending_action"]["payload"]["priority"],"P3")
        self.assertEqual(self.store.get_action(new["action_id"]),committed)
        self.assertEqual(len(self.mcp.writes),1)

    async def test_impact_clarification_asks_only_remaining_fact(self):
        for message,missing,known in [("I am completely blocked.","workaround","completely blocked"),
                                      ("I have no workaround.","blocked","workaround")]:
            with self.subTest(message=message):
                workflow=self.workflow()
                result=await self.chat(workflow,"CRM-1150. Please prepare a ticket. "+message,session=message)
                self.assertEqual(result["state"],"clarification")
                self.assertIn(missing,result["reply"])
                self.assertNotIn(known,result["reply"])
                self.assertEqual(workflow.script_calls,[])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.store = Store(self.data / "state.sqlite3")
        self.mcp, self.retrieval = FakeMCP(), FakeRetrieval()
        self.approvals = Approvals(self.store, self.mcp)

    def workflow(self, *script):
        # Existing shell credentials, if any, cannot trigger provider creation.
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}):
            return ScriptedWorkflow(self.store, self.mcp, self.retrieval, self.approvals,
                                    data_dir=self.data, script=script)

    async def chat(self, workflow, message="NakhlaID shows NID-423.", session="s"):
        return await workflow.chat(session, message, {"email": self.mcp.employee["email"]})

    def answer_script(self):
        return ({"action": "retrieve", "query": "NID-423"}, ANSWER, {"accepted": True, "complete": True})

    def timeout_workflow(self):
        with patch.dict(os.environ,{"OPENROUTER_API_KEY":""}):
            return TimeoutWorkflow(self.store,self.mcp,self.retrieval,self.approvals,data_dir=self.data,script=self.answer_script())

    async def test_read_selection_timeout_has_one_bounded_retry(self):
        workflow = self.timeout_workflow()
        result = await self.chat(workflow)
        self.assertEqual(result["state"],"answer")
        self.assertEqual(workflow.attempts["Decision"],2)
        self.assertEqual(workflow.attempts["Candidate"],1)
        self.assertEqual(workflow.attempts["Review"],1)
        self.assertEqual(self.mcp.writes,[])

    async def test_second_read_selection_timeout_stops_without_more_calls(self):
        workflow = self.timeout_workflow()
        workflow.failures = 2
        result = await self.chat(workflow)
        self.assertEqual(result["state"],"stopped")
        self.assertEqual(workflow.attempts,{"Decision":2})
        self.assertIsNone(result["pending_action"])
        self.assertEqual(self.mcp.writes,[])

    async def test_short_remaining_deadline_prevents_selection_retry(self):
        workflow = self.timeout_workflow()
        workflow.short_deadline = True
        result = await self.chat(workflow)
        self.assertEqual(result["state"],"stopped")
        self.assertEqual(workflow.attempts,{"Decision":1})
        self.assertEqual(self.mcp.writes,[])

    async def test_expensive_candidate_timeout_is_not_automatically_retried(self):
        workflow = self.timeout_workflow()
        workflow.failure_schema = "Candidate"
        result = await self.chat(workflow)
        self.assertEqual(result["state"],"stopped")
        self.assertEqual(workflow.attempts,{"Decision":1,"Candidate":1})
        self.assertIsNone(result["pending_action"])
        self.assertEqual(self.mcp.writes,[])

    async def test_truncated_issue_retains_documented_code_for_later_incident(self):
        self.mcp.employee["vpn_gateway"] = "GW-2"
        message = ("My NakhlaConnect VPN fails. " + "Connection detail. " * 175 +
                   " NX-503. I already restarted. I cannot work and have no workaround. Please open a ticket.")
        self.assertGreater(message.index("NX-503"), 3000)
        candidate = {"intent": "draft", "subject": "VPN connection failure", "description": "VPN fails.",
                     "attempted_steps": ["I already restarted."], "affected_users": 1}
        workflow = self.workflow({"action": "retrieve"}, candidate, {"accepted": True, "complete": True})
        result = await self.chat(workflow, message)
        self.assertEqual(result["state"], "await_confirmation", result["reply"])
        draft = result["pending_action"]
        self.mcp.status = {"incidents": [{"id": "INC-2207", "status": "active", "service": "vpn",
            "error_codes": ["NX-503"], "affected": "GW-2"}]}
        reply = await self.approvals.decide("s", draft["action_id"], True)
        self.assertEqual(self.mcp.writes, [])
        self.assertEqual(self.store.get_action(draft["action_id"])["status"], "superseded")
        self.assertIn("INC-2207", reply["reply"])
        self.assertIn("NX-503", draft["payload"]["description"])
        reviewer = next(packet for role, _, packet in workflow.script_calls if role == "Reviewer")
        self.assertEqual(reviewer["draft_payload_preview"], draft["payload"])
        self.assertLessEqual(len(draft["payload"]["description"]), 3000)

    def draft(self, attempts=None):
        return {"intent": "draft", "subject": "NakhlaConnect NX-403 cannot connect",
                "description": "NakhlaConnect NX-403 when connecting from home.",
                "attempted_steps": attempts or [], "affected_users": 1}

    async def test_graph_support_read_draft_independent_review_and_current_inline_citation(self):
        workflow = self.workflow(*self.answer_script())
        result = await self.chat(workflow)
        self.assertEqual(result["state"], "answer")
        self.assertEqual(result["reply"], "Wait 30 minutes. [KB-006]")
        self.assertEqual([c["id"] for c in result["citations"]], ["KB-006"])
        self.assertEqual([(r, s) for r, s, _ in workflow.script_calls],
                         [("Support", "Decision"), ("Support", "Candidate"), ("Reviewer", "Review")])
        self.assertEqual([c[0] for c in self.mcp.calls[:2]], ["get_service_status", "lookup_employee"])
        self.assertIn("retrieve", [c["tool"] for c in result["tool_calls"]])
        self.assertEqual(self.mcp.writes, [])

    async def test_reviewer_rejection_allows_one_correction_then_acceptance(self):
        workflow = self.workflow({"action": "retrieve"}, ANSWER,
                                 {"accepted": False, "complete": True, "corrections": "Be precise."}, {"claims":ANSWER["claims"]}, {"accepted": True, "complete": True})
        result = await self.chat(workflow)
        self.assertEqual(result["state"], "answer")
        self.assertEqual(len(workflow.script_calls), 5)
        self.assertEqual(workflow.script_calls[3][1],"ClaimsRevision")
        self.assertEqual(workflow.script_calls[3][2]["review"]["corrections"], "Be precise.")

    async def test_second_reviewer_rejection_stops_without_procedure(self):
        workflow = self.workflow({"action": "retrieve"}, ANSWER,
                                 {"accepted": False, "complete": True}, {"claims":ANSWER["claims"]}, {"accepted": False, "complete": True})
        result = await self.chat(workflow)
        self.assertEqual(result["state"], "unverified")
        self.assertNotIn("30 minutes", result["reply"])
        self.assertIsNone(result["pending_action"])
        self.assertEqual(len(workflow.script_calls), 5)

    async def test_noncurrent_or_invented_chunk_never_reaches_user(self):
        for bad in ("deprecated", "missing"):
            with self.subTest(kind=bad):
                self.retrieval.chunks = [copy.deepcopy(CHUNK)]
                if bad == "deprecated":
                    self.retrieval.chunks[0]["metadata"]["status"] = "deprecated"
                candidate = copy.deepcopy(ANSWER)
                if bad == "missing":
                    candidate["claims"][0]["chunk_ids"] = ["invented:chunk"]
                workflow = self.workflow({"action": "retrieve"}, candidate, {"accepted": True, "complete": True})
                result = await self.chat(workflow, session="bad-"+bad)
                self.assertEqual(result["state"], "stopped")
                self.assertEqual(result["citations"], [])
                self.assertNotIn("30 minutes", result["reply"])

    async def test_model_cannot_fabricate_attempted_steps(self):
        workflow = self.workflow({"action": "retrieve"}, self.draft(["I restarted my laptop"]), {"accepted": True, "complete": True})
        result = await self.chat(workflow, "My VPN shows NX-403. Please open a ticket. I am completely blocked and have no workaround.")
        self.assertEqual(result["state"], "stopped")
        self.assertIsNone(self.store.latest_action("s"))
        self.assertEqual(self.mcp.writes, [])

    async def test_no_attempts_requires_clarification_for_ordinary_requester(self):
        workflow = self.workflow({"action": "retrieve"}, self.draft(), {"accepted": True, "complete": True})
        result = await self.chat(workflow, "My VPN shows NX-403. Please open a ticket.")
        self.assertEqual(result["state"], "clarification")
        self.assertIsNone(result["pending_action"])

    async def test_finance_immediate_escalation_records_truthful_attempt_then_approval_only(self):
        self.mcp.employee = {"email": "fadi.mansour@nakhla.example", "department": "Finance", "vpn_gateway": "GW-3"}
        workflow = self.workflow({"action": "retrieve"}, self.draft(), {"accepted": True, "complete": True})
        result = await self.chat(workflow, "My Finance VPN on GW-3 shows NX-403. Prepare the required escalation.")
        self.assertEqual(result["state"], "await_confirmation")
        payload = result["pending_action"]["payload"]
        self.assertEqual(payload["attempted_steps"], [IMMEDIATE_ESCALATION])
        self.assertEqual(payload["category"], "security")
        self.assertEqual(self.mcp.writes, [])
        approved = await self.approvals.decide("s", result["pending_action"]["action_id"], True)
        self.assertEqual(approved["result"], {"ticket_id": "IT-2001"})
        self.assertEqual(self.mcp.writes[0][0], payload)

    async def test_contractor_vpn_policy_blocks_before_model_or_write(self):
        self.mcp.employee = {"email": "ziad.hourani@nakhla.example", "department": "Contractors", "contractor": True}
        workflow = self.workflow()
        result = await self.chat(workflow, "Please open a VPN access ticket.")
        self.assertEqual(result["state"], "refused")
        self.assertIn("vdi.nakhla.example", result["reply"])
        self.assertEqual(workflow.script_calls, [])
        self.assertEqual(self.mcp.writes, [])

    async def test_active_incident_matches_gateway_and_blocks_duplicate(self):
        self.mcp.employee["vpn_gateway"] = "GW-2"
        self.mcp.status = {"incidents": [{"id": "INC-2207", "status": "active", "service": "vpn",
            "error_codes": ["NX-503"], "affected": "Employees on GW-2", "workaround": "Use GW-1", "instructions": "Subscribe"}]}
        workflow = self.workflow()
        result = await self.chat(workflow, "My VPN shows NX-503. Please open a ticket.")
        self.assertEqual(result["state"], "active_incident")
        self.assertIn("INC-2207", result["reply"])
        self.assertIn("GW-1", result["reply"])
        self.assertIsNone(result["pending_action"])
        self.assertEqual(workflow.script_calls, [])
        self.mcp.employee = {"email": "fadi.mansour@nakhla.example", "department": "Finance", "vpn_gateway": "GW-3"}
        workflow = self.workflow({"action": "retrieve"}, self.draft(), {"accepted": True, "complete": True})
        result = await self.chat(workflow, "My Finance VPN shows NX-503. Prepare the escalation ticket.", session="finance")
        self.assertEqual(result["state"], "await_confirmation")

    async def test_identity_change_requires_new_session_and_invalidates_pending(self):
        self.store.save_session("s", {"email": EMPLOYEE["email"], "issue": "vpn"})
        workflow = self.workflow()
        result = await workflow.chat("s", "Help", {"email": "fadi.mansour@nakhla.example"})
        self.assertEqual(result["state"], "identity_changed")
        self.assertEqual(self.mcp.calls, [])
        self.assertEqual(self.store.get_session("s")["email"], EMPLOYEE["email"])

    async def test_retry_preserves_exact_payload_and_action_key_after_failure(self):
        self.mcp.employee = {"email": "fadi.mansour@nakhla.example", "department": "Finance", "vpn_gateway": "GW-3"}
        workflow = self.workflow({"action": "retrieve"}, self.draft(), {"accepted": True, "complete": True})
        first = await self.chat(workflow, "My Finance VPN shows NX-403. Prepare the escalation ticket.")
        pending = first["pending_action"]
        self.mcp.write_result = {"ok": False, "error": {"code": "http_503", "http_status": 503}}
        failed = await self.approvals.decide("s", pending["action_id"], True)
        self.assertIsNone(failed["result"])
        retry = await self.chat(workflow, "retry")
        self.assertEqual(retry["pending_action"], pending)
        self.assertEqual(len(self.mcp.writes), 1)
        self.mcp.write_result = {"ok": True, "ticket": {"ticket_id": "IT-2001"}}
        await self.approvals.decide("s", pending["action_id"], True)
        self.assertEqual(self.mcp.writes[0], self.mcp.writes[1])

    async def test_status_failure_blocks_guidance_and_draft(self):
        self.mcp.status_ok = False
        workflow = self.workflow()
        result = await self.chat(workflow, "My VPN shows NX-503. Open a ticket.")
        self.assertEqual(result["state"], "dependency_unavailable")
        self.assertIsNone(result["pending_action"])
        self.assertEqual(workflow.script_calls, [])

    async def test_missing_live_prerequisite_returns_explicit_not_ready_after_reads(self):
        for missing in ("credential", "index"):
            workflow = self.workflow()
            if missing == "credential":
                workflow.client = None
            else:
                self.retrieval.ready = False
            result = await self.chat(workflow, session="missing-"+missing)
            self.assertEqual(result["state"], "not_ready")
            self.assertEqual(workflow.script_calls, [])
            self.assertEqual(self.mcp.writes, [])

    async def test_followup_context_survives_store_reopen(self):
        workflow = self.workflow({"action": "clarify", "question": "Which error code do you see?"})
        await self.chat(workflow, "My VPN does not connect.")
        reopened = Store(self.data / "state.sqlite3")
        self.assertIn("VPN", reopened.get_session("s")["issue"])
        self.store = reopened
        workflow = self.workflow(*self.answer_script())
        await self.chat(workflow, "The code is NX-781.")
        packet = workflow.script_calls[0][2]
        self.assertEqual(packet["context"]["error_code"], "NX-781")
        self.assertIn("My VPN does not connect", packet["context"]["issue"])
        self.assertEqual(packet["employee"]["email"], EMPLOYEE["email"])

    async def test_new_issue_clears_old_incident_error_context(self):
        self.mcp.employee["vpn_gateway"] = "GW-2"
        self.mcp.status = {"incidents": [{"id": "INC-2207", "status": "active", "service": "vpn",
            "error_codes": ["NX-503"], "affected": "Employees on GW-2", "workaround": "Use GW-1", "instructions": "Subscribe"}]}
        workflow = self.workflow()
        first = await self.chat(workflow, "My VPN shows NX-503.")
        self.assertEqual(first["state"], "active_incident")
        workflow = self.workflow({"action": "clarify", "question": "Which printer is jammed?"})
        second = await self.chat(workflow, "New issue: the printer has a paper jam.")
        self.assertNotEqual(second["state"], "active_incident")
        self.assertNotIn("INC-2207", second["reply"])
        self.assertEqual(self.store.get_session("s")["error_code"], "")

    async def test_clarification_cannot_bypass_output_id_or_secret_guards(self):
        workflow = self.workflow({"action": "clarify", "question": "Your ticket is IT-2999. Is that okay?"})
        result = await self.chat(workflow)
        self.assertNotIn("IT-2999", result["reply"])
        self.assertIsNone(result["result"])

    async def test_pending_payload_cannot_leak_model_invented_id_or_secret(self):
        self.mcp.employee = {"email": "fadi.mansour@nakhla.example", "department": "Finance", "vpn_gateway": "GW-3"}
        for unsafe in ("The ticket is IT-2999 already.", "The password is private-demo-secret."):
            with self.subTest(payload=unsafe):
                candidate = self.draft()
                candidate["description"] = unsafe
                workflow = self.workflow({"action": "retrieve"}, candidate, {"accepted": True, "complete": True})
                result = await self.chat(workflow, "My Finance VPN shows NX-403. Prepare an escalation ticket.", session="payload-"+str(len(unsafe)))
                self.assertNotIn(unsafe, result["reply"])
                if "IT-2999" in unsafe:
                    # Batch 8: the model description is discarded and replaced by the source-bound one
                    # before review, so a model-invented id there can no longer reach any output. The
                    # draft is built only from requester text; the id appears nowhere.
                    self.assertEqual(result["state"], "await_confirmation")
                    self.assertNotIn("IT-2999", json.dumps(result))
                    self.assertNotIn("IT-2999", json.dumps(self.store.latest_action("payload-"+str(len(unsafe)))))
                    self.assertEqual(self.mcp.writes, [])
                else:
                    self.assertIsNone(result["pending_action"])   # a credential is still blocked
                    self.assertIsNone(self.store.latest_action("payload-"+str(len(unsafe))))

    async def test_unknown_error_rejects_adjacent_fix_but_permits_requested_escalation(self):
        workflow = self.workflow({"action": "retrieve"}, ANSWER, {"accepted": True, "complete": True})
        result = await self.chat(workflow, "The app shows CRM-1150. What fixes that?", session="unknown-answer")
        self.assertEqual(result["state"], "unknown")
        self.assertNotIn("30 minutes", result["reply"])
        self.assertEqual(result["citations"], [])
        draft = self.draft(["I restarted the app"])
        draft.update(subject="CRM-1150 sync failure", description="CRM-1150 still appears after restarting the app.",
                     claims=copy.deepcopy(ANSWER["claims"]))
        workflow = self.workflow({"action": "retrieve"}, draft, {"accepted": True, "complete": True})
        result = await self.chat(workflow, "CRM-1150 still fails. I restarted the app. Please open a ticket. I am completely blocked and have no workaround.", session="unknown-draft")
        self.assertEqual(result["state"], "await_confirmation")
        self.assertEqual(result["pending_action"]["payload"]["kb_refs"], [])
        self.assertEqual(result["pending_action"]["payload"]["attempted_steps"], ["I restarted the app"])
        self.assertEqual(self.mcp.writes, [])

    async def test_failed_retrieval_retains_billed_query_cost_in_response_usage(self):
        workflow = self.workflow({"action": "retrieve"})

        async def billed_failure(query, department=None):
            reservation = workflow.ledger.reserve(.001, "offline-test-query-accounting")
            workflow.ledger.settle(reservation, .0005, actual=False)
            raise RuntimeError("Injected failure after accounting; no provider called")

        self.retrieval.search = billed_failure
        result = await self.chat(workflow)
        self.assertEqual(result["state"], "stopped")
        self.assertAlmostEqual(result["usage"]["cost_usd"], .0005)

    async def test_implicit_distinct_printer_issue_clears_old_vpn_error(self):
        self.mcp.employee["vpn_gateway"] = "GW-2"
        self.mcp.status = {"incidents": [{"id": "INC-2207", "status": "active", "service": "vpn",
            "error_codes": ["NX-503"], "affected": "Employees on GW-2", "workaround": "Use GW-1", "instructions": "Subscribe"}]}
        workflow = self.workflow()
        await self.chat(workflow, "My VPN shows NX-503.")
        workflow = self.workflow({"action": "clarify"})
        result = await self.chat(workflow, "My printer has a paper jam.")
        self.assertNotEqual(result["state"], "active_incident")
        self.assertEqual(self.store.get_session("s")["error_code"], "")
        self.assertEqual(self.store.get_session("s")["topic"], "hardware")

    async def test_typed_requester_facts_and_last_supported_answer_persist(self):
        vpn_answer={"intent":"answer","claims":[{"text":"NX-781 requires client 5.4 or later.","chunk_ids":[VPN_CHUNK["chunk_id"]]}]}
        workflow = self.workflow({"action":"retrieve","query":"NX-781"},vpn_answer,{"accepted":True,"complete":True})
        first = await self.chat(workflow, "NakhlaConnect VPN shows NX-781 on Windows 11, client version 5.1.")
        stored = self.store.get_session("s")
        self.assertEqual(stored["facts"]["os"]["value"], "Windows 11")
        self.assertEqual(stored["facts"]["client_version"]["value"], "5.1")
        self.assertEqual(stored["facts"]["os"]["source"], "requester")
        self.assertEqual(stored["last_supported_answer"]["reply"], first["reply"])
        workflow = self.workflow({"action": "clarify"})
        await self.chat(workflow, "It still fails.")
        packet = workflow.script_calls[0][2]["context"]
        self.assertEqual(packet["facts"]["client_version"]["value"], "5.1")
        self.assertEqual(packet["last_supported_answer"]["reply"], first["reply"])

    async def test_vague_vpn_known_employee_asks_error_before_model(self):
        for index,message in enumerate(("My VPN will not connect from home.",
                "how to fix vpn no working", "VPN doesn't work", "VPN connection keeps failing",
                "Need help with my VPN", "NakhlaConnect connection problem")):
            with self.subTest(message=message):
                self.mcp.calls.clear()
                workflow = self.workflow()
                result = await self.chat(workflow,message,session=f"vague-{index}")
                self.assertEqual(result["state"],"clarification")
                self.assertIn("error code",result["reply"])
                self.assertNotRegex(result["reply"],r"\bP[1-4]\b|5\.4")
                self.assertIsNone(result["pending_action"])
                self.assertEqual(workflow.script_calls,[])
                self.assertEqual([name for name,_ in self.mcp.calls],["get_service_status","lookup_employee"])
                self.assertEqual(self.mcp.writes,[])

    async def test_vague_vpn_bare_code_followup_preserves_requester(self):
        workflow=self.workflow()
        first=await self.chat(workflow,"how to fix vpn no working")
        self.assertEqual(first["state"],"clarification")
        chunk=copy.deepcopy(VPN_CHUNK)
        chunk["text"]="Minimum supported client: 5.4. Recommended client: 5.4.2 from Software Center; restart NakhlaConnect."
        self.retrieval.chunks=[chunk]
        answer={"intent":"answer","claims":[{"text":chunk["text"],"chunk_ids":[chunk["chunk_id"]]}]}
        workflow=self.workflow({"action":"retrieve"},answer,{"accepted":True,"complete":True})
        result=await workflow.chat("s","NX-781",{"email":self.mcp.employee["email"]})
        self.assertEqual(result["state"],"answer")
        self.assertIn("Minimum supported client: 5.4.",result["reply"])
        self.assertIn("Recommended client: 5.4.2",result["reply"])
        self.assertEqual([c["id"] for c in result["citations"]],["KB-002"])
        self.assertIsNone(result["pending_action"])
        context=self.store.get_session("s")
        self.assertEqual(context["email"],self.mcp.employee["email"])
        self.assertEqual(context["topic"],"vpn")
        self.assertEqual(context["error_code"],"NX-781")
        self.assertEqual(self.mcp.writes,[])

    async def test_vague_vpn_preserves_department_exceptions(self):
        self.mcp.employee={"email":"fadi.mansour@nakhla.example","department":"Finance","vpn_gateway":"GW-3"}
        draft=self.draft()
        draft.update(subject="VPN cannot connect",description="VPN is not working.")
        workflow=self.workflow({"action":"retrieve"},draft,{"accepted":True,"complete":True})
        result=await self.chat(workflow,"how to fix vpn no working",session="finance-vague")
        self.assertEqual(result["state"],"await_confirmation")
        self.assertEqual(result["pending_action"]["payload"]["attempted_steps"],[IMMEDIATE_ESCALATION])
        self.assertEqual(result["pending_action"]["payload"]["category"],"security")
        self.assertEqual(self.mcp.writes,[])
        self.mcp.employee={"email":"ziad.hourani@nakhla.example","department":"Contractors","contractor":True}
        workflow=self.workflow()
        result=await self.chat(workflow,"how to fix vpn no working",session="contractor-vague")
        self.assertEqual(result["state"],"refused")
        self.assertIn("SP-002",result["reply"])
        self.assertEqual(workflow.script_calls,[])
        self.assertEqual(self.mcp.writes,[])

    async def test_vague_vpn_incident_code_followup_takes_incident_gate(self):
        self.mcp.employee["vpn_gateway"]="GW-2"
        self.mcp.status={"incidents":[{"id":"INC-2207","status":"active","service":"vpn",
            "error_codes":["NX-503"],"affected":"Employees on GW-2","workaround":"Use GW-1","instructions":"Subscribe"}]}
        workflow=self.workflow()
        first=await self.chat(workflow,"VPN doesn't work")
        self.assertEqual(first["state"],"clarification")
        result=await workflow.chat("s","NX-503",{"email":self.mcp.employee["email"]})
        self.assertEqual(result["state"],"active_incident")
        self.assertIn("INC-2207",result["reply"])
        self.assertIn("KB-015",result["reply"])
        self.assertIsNone(result["pending_action"])
        self.assertEqual(workflow.script_calls,[])
        self.assertEqual(self.mcp.writes,[])

    async def test_incident_then_crm_then_nothing_tried_keeps_only_crm_issue(self):
        self.mcp.employee={"email":"omar.farah@nakhla.example","department":"Sales","vpn_gateway":"GW-2"}
        self.mcp.status={"incidents":[{"id":"INC-2207","status":"active","service":"vpn",
            "error_codes":["NX-503"],"affected":"Employees on GW-2","workaround":"Use GW-1","instructions":"Subscribe"}]}
        workflow=self.workflow()
        first=await self.chat(workflow,"My VPN shows NX-503. Please open a ticket.")
        self.assertEqual(first["state"],"active_incident")
        crm="The NakhlaCRM mobile app shows CRM-1150 when syncing contacts. How do I fix it?"
        workflow=self.workflow({"action":"retrieve"})
        second=await workflow.chat("s",crm,{"email":self.mcp.employee["email"]})
        self.assertEqual(second["state"],"unknown")
        stored=self.store.get_session("s")
        self.assertNotIn("VPN",stored["issue"])
        self.assertNotIn("NX-503",stored["issue"])
        self.assertEqual(stored["error_code"],"CRM-1150")
        self.assertNotEqual(stored["topic"],"vpn")
        self.assertEqual(stored["messages"],[crm])
        self.assertFalse(requested_draft(stored["issue"]))
        draft={"intent":"draft","subject":"NakhlaCRM CRM-1150 contact sync failure",
               "description":"NakhlaCRM mobile app contact sync fails with CRM-1150.","attempted_steps":[],"affected_users":1}
        workflow=self.workflow({"action":"retrieve"},draft,{"accepted":True,"complete":True})
        third=await workflow.chat("s","I haven’t tried anything yet. Please prepare a ticket.",{"email":self.mcp.employee["email"]})
        self.assertEqual(third["state"],"clarification")
        self.assertIn("workaround",third["reply"])
        self.assertNotIn("error code",third["reply"])
        third=await workflow.chat("s","I can still work using a documented workaround.",{"email":self.mcp.employee["email"]})
        self.assertEqual(third["state"],"await_confirmation")
        payload=third["pending_action"]["payload"]
        self.assertEqual(payload["attempted_steps"],["I haven’t tried anything yet."])
        self.assertIn("CRM-1150",payload["description"])
        self.assertIn("syncing contacts",payload["description"])
        self.assertNotIn("NX-503",payload["description"])
        self.assertEqual(payload["requester_email"],self.mcp.employee["email"])
        self.assertEqual(self.mcp.writes,[])
        rejected=await self.approvals.decide("s",third["pending_action"]["action_id"],False)
        self.assertFalse(rejected.get("result"))
        self.assertEqual(self.mcp.writes,[])

    def test_nothing_tried_is_verbatim_history_not_invented_remediation(self):
        for phrase in ["I haven’t tried anything yet.","I haven't tried anything yet.",
                       "I have not tried anything yet.","I tried nothing."]:
            with self.subTest(phrase=phrase):
                self.assertEqual(source_attempts([phrase]),[phrase])
        self.assertEqual(source_attempts(["I have not tried restarting the client."]),[])
        self.assertFalse(explicitly_nothing_tried("I haven't tried anything except restarting the VPN."))
        self.assertFalse(explicitly_nothing_tried("I haven't tried anything other than restarting the VPN."))

    async def test_finance_explicit_nothing_tried_preserves_canonical_entry(self):
        self.mcp.employee={"email":"fadi.mansour@nakhla.example","department":"Finance","vpn_gateway":"GW-3"}
        workflow=self.workflow({"action":"retrieve"},self.draft(["I haven’t tried anything yet."]),
                               {"accepted":True,"complete":True})
        result=await self.chat(workflow,"My VPN shows NX-403. I haven’t tried anything yet. Please prepare a ticket.")
        self.assertEqual(result["state"],"await_confirmation")
        self.assertEqual(result["pending_action"]["payload"]["attempted_steps"],[IMMEDIATE_ESCALATION])
        self.assertEqual(workflow.script_calls[-1][2]["draft_payload_preview"]["attempted_steps"],[IMMEDIATE_ESCALATION])
        self.assertEqual(self.mcp.writes,[])

    async def test_non_catalogue_software_requires_each_of_four_source_facts(self):
        self.mcp.employee={"email":"dalia.awwad@nakhla.example","department":"Executive Office","vip":True}
        message="Please prepare a software request ticket for Inkscape. I searched Software Center and it is not listed."
        all_fields={"app_name":"Inkscape","version":"1.4","business_reason":"prepare board meeting diagrams","manager":"Rana Khalil"}
        for missing in [None,*all_fields]:
            with self.subTest(missing=missing):
                details=copy.deepcopy(all_fields) if missing else None
                if missing:
                    details[missing]=""
                candidate={"intent":"draft","subject":"Inkscape software request","description":"Software request for Inkscape.",
                           "attempted_steps":["I searched Software Center and it is not listed."],"software_request":details}
                workflow=self.workflow({"action":"retrieve"},candidate)
                session="missing-software-"+str(missing)
                result=await self.chat(workflow,message,session=session)
                self.assertEqual(result["state"],"clarification")
                self.assertIn("version",result["reply"])
                self.assertIn("manager",result["reply"])
                self.assertIsNone(result["pending_action"])
                self.assertIsNone(self.store.latest_action(session))
                self.assertEqual(self.mcp.writes,[])
                self.assertFalse(any(role=="Reviewer" for role,_,_ in workflow.script_calls))

    async def test_complete_software_request_is_vip_p1_and_description_quotes_source(self):
        self.mcp.employee={"email":"dalia.awwad@nakhla.example","department":"Executive Office","vip":True}
        message=("Please prepare a software request ticket for Inkscape version 1.4. "
                 "Business reason: prepare board meeting diagrams. Manager: Rana Khalil. "
                 "I searched Software Center and Inkscape is not listed; this is a request, not an outage.")
        attempt="I searched Software Center and Inkscape is not listed; this is a request, not an outage."
        details={"app_name":"Inkscape","version":"1.4","business_reason":"prepare board meeting diagrams","manager":"Rana Khalil"}
        candidate={"intent":"draft","subject":"Inkscape version 1.4 software request",
                   "description":"The user is completely blocked and requires urgent handling.",
                   "attempted_steps":[attempt],"software_request":details}
        workflow=self.workflow({"action":"retrieve"},candidate,{"accepted":True,"complete":True})
        result=await self.chat(workflow,message)
        self.assertEqual(result["state"],"await_confirmation")
        payload=result["pending_action"]["payload"]
        self.assertEqual((payload["category"],payload["priority"]),("software","P1"))
        self.assertEqual(payload["description"],"Requester reported: "+self.store.get_session("s")["issue"])
        self.assertNotIn("urgent",payload["description"])
        self.assertNotIn("completely blocked",payload["description"])
        for fact in details.values():
            self.assertIn(fact,payload["description"])
        self.assertEqual(payload["attempted_steps"],[attempt])
        self.assertEqual(self.mcp.writes,[])
        self.assertEqual(workflow.script_calls[-1][2]["candidate"]["description"],payload["description"])

    async def test_software_request_cannot_invent_a_missing_manager(self):
        self.mcp.employee={"email":"dalia.awwad@nakhla.example","department":"Executive Office","vip":True}
        message=("Please prepare a software request for Inkscape version 1.4 to prepare board meeting diagrams. "
                 "I searched Software Center and it is not listed.")
        candidate={"intent":"draft","subject":"Inkscape software request","description":"Inkscape is not listed.",
                   "attempted_steps":["I searched Software Center and it is not listed."],
                   "software_request":{"app_name":"Inkscape","version":"1.4","business_reason":"prepare board meeting diagrams","manager":"Invented Manager"}}
        workflow=self.workflow({"action":"retrieve"},candidate)
        result=await self.chat(workflow,message)
        self.assertEqual(result["state"],"clarification")
        self.assertIn("manager",result["reply"])
        self.assertIsNone(result["pending_action"])
        self.assertIsNone(self.store.latest_action("s"))
        self.assertEqual(self.mcp.writes,[])
        self.assertFalse(any(role=="Reviewer" for role,_,_ in workflow.script_calls))

    async def test_claim_revision_cannot_change_draft_intent_or_payload(self):
        self.mcp.employee={"email":"fadi.mansour@nakhla.example","department":"Finance","vpn_gateway":"GW-3"}
        malicious_revision={"claims":ANSWER["claims"],"subject":"Unexpected replacement subject"}
        workflow=self.workflow({"action":"retrieve"},self.draft(),
                               {"accepted":False,"complete":True,"corrections":"Use Finance routing claims only."},malicious_revision)
        result=await self.chat(workflow,"My Finance VPN shows NX-403. Prepare the required escalation.")
        self.assertEqual(result["state"],"stopped")
        self.assertIsNone(result["pending_action"])
        self.assertIsNone(self.store.latest_action("s"))
        self.assertEqual(self.mcp.writes,[])
        self.assertEqual(len(workflow.script_calls),4)
        self.assertEqual(workflow.script_calls[-1][1],"ClaimsRevision")

    async def test_negated_ticket_request_cannot_become_a_draft(self):
        candidate=self.draft(["I restarted the laptop"])
        workflow=self.workflow({"action":"retrieve"},candidate,{"accepted":True,"complete":True})
        result=await self.chat(workflow,"My VPN shows NX-403. I restarted the laptop. I am not asking to open a ticket.")
        self.assertEqual(result["state"],"stopped")
        self.assertIsNone(result["pending_action"])
        self.assertIsNone(self.store.latest_action("s"))
        self.assertEqual(self.mcp.writes,[])

    async def test_missing_review_completeness_fails_schema_and_stops(self):
        workflow=self.workflow({"action":"retrieve"},ANSWER,{"accepted":True})
        result=await self.chat(workflow)
        self.assertEqual(result["state"],"stopped")
        self.assertIsNone(result["pending_action"])
        self.assertNotIn("30 minutes",result["reply"])
        self.assertEqual(len(workflow.script_calls),3)
        self.assertEqual(self.mcp.writes,[])

    async def test_accepted_but_incomplete_review_requires_bounded_revision(self):
        workflow=self.workflow({"action":"retrieve"},ANSWER,
                               {"accepted":True,"complete":False,"corrections":"Answer the other requested part."},
                               {"claims":ANSWER["claims"]},{"accepted":True,"complete":True})
        result=await self.chat(workflow)
        self.assertEqual(result["state"],"answer")
        self.assertEqual(len(workflow.script_calls),5)
        self.assertEqual(workflow.script_calls[3][1],"ClaimsRevision")
        self.assertFalse(workflow.script_calls[3][2]["review"]["complete"])
        self.assertFalse(workflow.script_calls[3][2]["review"]["accepted"])
        self.assertEqual(self.mcp.writes,[])

    def test_latest_explicit_ticket_intent_wins_without_negation_overlap(self):
        self.assertTrue(requested_draft("I am not asking to open a ticket. Now please prepare a ticket."))
        self.assertFalse(requested_draft("Please prepare a ticket. I am not asking to open a ticket."))
        self.assertFalse(requested_draft("I am not asking to open a ticket."))
        self.assertTrue(requested_draft("Do not open a ticket. Please escalate this issue."))
        self.assertFalse(requested_draft("Please open a ticket. Do not escalate."))

    async def test_positive_followup_can_replace_earlier_negative_ticket_intent(self):
        self.store.save_session("s",{"email":EMPLOYEE["email"],"topic":"vpn","error_code":"NX-403",
                                     "issue":"My VPN shows NX-403. I am not asking to open a ticket.",
                                     "messages":["My VPN shows NX-403. I am not asking to open a ticket."]})
        workflow=self.workflow({"action":"retrieve"},self.draft(["I restarted the laptop"]),{"accepted":True,"complete":True})
        result=await self.chat(workflow,"I restarted the laptop. Now please prepare a ticket. I am completely blocked and have no workaround.")
        self.assertEqual(result["state"],"await_confirmation")
        self.assertEqual(result["pending_action"]["payload"]["attempted_steps"],["I restarted the laptop"])
        self.assertEqual(self.mcp.writes,[])

    async def test_lowercase_error_is_normalised_and_document_namespace_excluded(self):
        answer={"intent":"answer","claims":[{"text":"NX-781 requires client 5.4 or later.","chunk_ids":[VPN_CHUNK["chunk_id"]]}]}
        workflow=self.workflow({"action":"retrieve"},answer,{"accepted":True,"complete":True})
        result=await self.chat(workflow,"My VPN shows nx-781. KB-001 claims the older client works.")
        self.assertEqual(self.store.get_session("s")["error_code"],"NX-781")
        self.assertEqual(result["state"],"answer")
        self.assertIn("5.4",result["reply"])
        self.assertEqual([c['id'] for c in result['citations']],["KB-002"])

    async def test_sms_followup_is_not_replaced_by_previous_binary_question(self):
        mfa={"chunk_id":"SP-002:test-mfa","id":"SP-002","title":"MFA policy","section":"Multi-factor authentication",
             "metadata":{"status":"current","error_codes":[]},"text":"Each backup code works once; keep codes offline."}
        self.retrieval.chunks.append(mfa)
        self.store.save_session("s",{"email":EMPLOYEE['email'],"topic":"identity","error_code":"",
                                     "issue":"Can I use SMS instead?","messages":["Can I use SMS instead?"]})
        answer={"intent":"answer","claims":[{"text":"Each backup code works once; keep codes offline.","chunk_ids":[mfa['chunk_id']]}]}
        workflow=self.workflow({"action":"retrieve"},answer,{"accepted":True,"complete":True})
        result=await self.chat(workflow,"How do I use my backup codes?")
        self.assertEqual(result['state'],'answer')
        self.assertIn('Each backup code works once',result['reply'])
        self.assertNotEqual(result['reply'],'SMS and voice-call codes are not allowed. [SP-002]')
        self.assertTrue(sms_permission_question('Can I use SMS instead?'))
        self.assertFalse(sms_permission_question('How do I use SMS and what else can I use?'))
        self.assertEqual(claim_capacity('How early must the form be submitted, and who receives the link?'),2)

    async def test_history_read_uses_actual_owned_records_not_stale_incident(self):
        self.mcp.employee['vpn_gateway']='GW-2'
        self.store.save_session('s',{'email':EMPLOYEE['email'],'topic':'vpn','error_code':'NX-503',
                                    'issue':'My VPN shows NX-503.','messages':['My VPN shows NX-503.']})
        self.mcp.status={'incidents':[{'id':'INC-2207','status':'active','service':'vpn','error_codes':['NX-503'],
                                     'affected':'Employees on GW-2','workaround':'Use GW-1','instructions':'Subscribe'}]}
        self.mcp.tickets=[{'ticket_id':'IT-1001','requester_email':EMPLOYEE['email'],'subject':'Own previous VPN issue','status':'resolved'},
                          {'ticket_id':'IT-1002','requester_email':'other@nakhla.example','subject':'Private other issue','status':'open'}]
        workflow=self.workflow({'action':'history'})
        result=await self.chat(workflow,'Show my ticket history.')
        self.assertEqual(result['state'],'history')
        self.assertIn('IT-1001: Own previous VPN issue',result['reply'])
        self.assertNotIn('IT-1002',result['reply'])
        self.assertNotIn('Private other issue',result['reply'])
        self.assertNotIn('INC-2207',result['reply'])
        self.assertEqual(len(workflow.script_calls),0)  # list requests are deterministic now
        self.assertEqual(self.retrieval.queries,[])
        self.assertEqual(self.mcp.writes,[])

    async def test_explicit_get_ticket_checks_owner_before_rendering(self):
        for owned in (True,False):
            with self.subTest(owned=owned):
                self.mcp.tickets=[{'ticket_id':'IT-1001','requester_email':EMPLOYEE['email'] if owned else 'other@nakhla.example',
                                   'subject':'Own history' if owned else 'Private other history','status':'resolved'}]
                workflow=self.workflow({'action':'get_ticket','ticket_id':'IT-1001'})
                result=await self.chat(workflow,'Show ticket IT-1001.',session='owner-'+str(owned))
                self.assertEqual(result['state'],'history' if owned else 'refused')
                if not owned:
                    self.assertIn('not available for your account',result['reply'])
                if owned:
                    self.assertIn('IT-1001',result['reply'])
                else:
                    self.assertNotIn('Private other history',result['reply'])
                self.assertIsNone(result['pending_action'])
                self.assertEqual(self.mcp.writes,[])

    async def test_ticket_history_is_not_blocked_by_stale_contractor_vpn_refusal(self):
        self.mcp.employee={'email':'ziad.hourani@nakhla.example','department':'Contractors','contractor':True}
        self.store.save_session('s',{'email':self.mcp.employee['email'],'topic':'vpn','error_code':'NX-403',
                                    'issue':'I requested VPN access.','messages':['I requested VPN access.']})
        self.mcp.tickets=[{'ticket_id':'IT-1001','requester_email':self.mcp.employee['email'],
                          'subject':'Own earlier VDI portal issue','status':'resolved'}]
        workflow=self.workflow({'action':'history'})
        result=await self.chat(workflow,'Show my previous tickets.')
        self.assertEqual(result['state'],'history')
        self.assertIn('Own earlier VDI portal issue',result['reply'])
        self.assertNotIn('refused',result['reply'])
        self.assertEqual(self.retrieval.queries,[])
        self.assertEqual(self.mcp.writes,[])

    async def test_model_cannot_fetch_an_unmentioned_ticket_id(self):
        workflow=self.workflow({'action':'get_ticket','ticket_id':'IT-1002'})
        result=await self.chat(workflow,'Show ticket IT-1001.')
        self.assertEqual(result['state'],'stopped')
        self.assertFalse(any(name=='get_ticket' for name,_ in self.mcp.calls))
        self.assertIsNone(result['pending_action'])
        self.assertEqual(self.mcp.writes,[])

    RECALL_QUESTION = "Which VPN error did I report, and what troubleshooting did I say I tried?"

    async def report_vpn_ticket(self, session="s"):
        first = await self.chat(self.workflow({"action": "retrieve"}), "My VPN shows NX-999. What should I do?", session)
        self.assertEqual(first["state"], "unknown")
        draft = {"intent": "draft", "subject": "NakhlaConnect NX-999", "description": "VPN shows NX-999.",
                 "attempted_steps": [], "affected_users": 1}
        workflow = self.workflow({"action": "retrieve"}, draft, {"accepted": True, "complete": True})
        second = await self.chat(workflow, "I have not tried anything yet. I can continue working without the VPN. Please prepare a ticket.", session)
        self.assertEqual(second["state"], "await_confirmation")
        return second["pending_action"]

    async def assert_recall_without_side_effects(self, message, session="s"):
        before = copy.deepcopy(self.store.get_session(session))
        writes, calls = len(self.mcp.writes), len(self.mcp.calls)
        status = self.store.latest_action(session)["status"]
        expected = "superseded" if status in ("pending", "failed") else status
        workflow = self.workflow()
        result = await self.chat(workflow, message, session)
        self.assertEqual(result["state"], "recall")
        self.assertEqual(workflow.script_calls, [])
        self.assertEqual((len(self.mcp.writes), len(self.mcp.calls)), (writes, calls))
        self.assertIsNone(result["pending_action"])
        self.assertEqual(result["citations"], [])
        self.assertNotIn("[KB", result["reply"])
        self.assertEqual(self.store.get_session(session), before)
        self.assertEqual(self.store.latest_action(session)["status"], expected)
        return result

    async def test_reported_recall_sequence_after_approval_and_rejection(self):
        for approve in (True, False):
            with self.subTest(approve=approve):
                session = "approved" if approve else "rejected"
                self.mcp.writes.clear()
                pending = await self.report_vpn_ticket(session)
                outcome = await self.approvals.decide(session, pending["action_id"], approve)
                self.assertEqual(bool(outcome.get("result")), approve)
                self.assertEqual(len(self.mcp.writes), 1 if approve else 0)
                result = await self.assert_recall_without_side_effects(self.RECALL_QUESTION, session)
                self.assertIn("NX-999", result["reply"])
                self.assertIn("no troubleshooting", result["reply"].lower())
                self.assertNotIn("What have you already tried", result["reply"])
                self.assertEqual(len(self.mcp.writes), 1 if approve else 0)
                self.assertEqual(self.store.get_session(session)["draft_pending"], "draft")

    async def test_recall_paraphrases_are_answered_from_the_conversation(self):
        await self.report_vpn_ticket()
        for question in ["What error code did I tell you about earlier?",
                         "Can you remind me what I reported and whether I tried anything?",
                         "Which error did I mention, and have I already tried any fixes?",
                         "what did I say I tried?",
                         "Remind me which VPN error I reported."]:
            with self.subTest(question=question):
                self.assertTrue(conversation_recall(question, "NX-999"))
                result = await self.assert_recall_without_side_effects(question)
                self.assertTrue("NX-999" in result["reply"] or "no troubleshooting" in result["reply"].lower())

    def test_recall_detection_does_not_swallow_real_requests(self):
        for text in ["How do I fix NX-999?", "What should I do about it?", "Please prepare that same ticket again.",
                     "I tried restarting the VPN client.", "My VPN shows NX-403. Which gateway should I use?",
                     "Can you show ticket IT-2001?", "What is the company policy on MFA?",
                     "I have not tried anything yet.", "This is a new issue: which printer should I use?"]:
            with self.subTest(text=text):
                self.assertFalse(conversation_recall(text, "NX-999"))

    def test_questions_are_not_recorded_as_troubleshooting_attempts(self):
        self.assertEqual(source_attempts([self.RECALL_QUESTION]), [])
        for question in ["What troubleshooting did I say I tried?", "Did I try restarting the client?",
                         "Have I already tried the VPN reset?", "Which steps did I tell you about?",
                         "Remind me what I tried."]:
            with self.subTest(question=question):
                self.assertEqual(source_attempts([question]), [])
        self.assertEqual(source_attempts(["My VPN shows NX-999. I tried restarting the client."]),
                         ["I tried restarting the client."])
        self.assertEqual(source_attempts(["I tried restarting the client. Which VPN error did I report?"]),
                         ["I tried restarting the client."])
        self.assertEqual(source_attempts(["I have not tried anything yet."]), ["I have not tried anything yet."])

    async def test_recall_reports_genuine_attempts_and_nothing_tried_separately(self):
        await self.chat(self.workflow({"action": "retrieve"}), "My VPN shows NX-999. I tried restarting the client and rebooting. What should I do?")
        workflow = self.workflow()
        result = await self.chat(workflow, "Which VPN error did I report, and what did I try?")
        self.assertEqual((result["state"], workflow.script_calls, self.mcp.writes), ("recall", [], []))
        self.assertIn("NX-999", result["reply"])
        self.assertIn("restarting the client", result["reply"])
        self.assertNotIn("no troubleshooting", result["reply"].lower())
        await self.chat(self.workflow({"action": "retrieve"}), "My VPN shows NX-998. I have not tried anything yet. What should I do?", "other")
        recalled = await self.chat(self.workflow(), "What did I say I tried?", "other")
        self.assertEqual(recalled["state"], "recall")
        self.assertIn("no troubleshooting", recalled["reply"].lower())

    async def test_recall_without_a_prior_conversation_is_not_invented(self):
        workflow = self.workflow()
        result = await self.chat(workflow, "Which error did I report?", "fresh")
        self.assertNotEqual(result["state"], "recall")
        self.assertEqual(self.mcp.writes, [])

    async def test_recall_does_not_authorise_or_reuse_an_old_ticket_request(self):
        pending = await self.report_vpn_ticket()
        await self.approvals.decide("s", pending["action_id"], True)
        await self.assert_recall_without_side_effects(self.RECALL_QUESTION)
        workflow = self.workflow({"action": "retrieve"}, ANSWER, {"accepted": True, "complete": True})
        result = await self.chat(workflow, "Thanks, the VPN still shows the same code.")
        self.assertNotEqual(result["state"], "await_confirmation")
        self.assertIsNone(result["pending_action"])
        self.assertEqual(len(self.mcp.writes), 1)

    async def test_explicit_new_ticket_request_after_recall_still_drafts(self):
        pending = await self.report_vpn_ticket()
        await self.approvals.decide("s", pending["action_id"], False)
        await self.assert_recall_without_side_effects(self.RECALL_QUESTION)
        draft = {"intent": "draft", "subject": "NakhlaConnect NX-999", "description": "VPN shows NX-999.",
                 "attempted_steps": [], "affected_users": 1}
        workflow = self.workflow({"action": "retrieve"}, draft, {"accepted": True, "complete": True})
        result = await self.chat(workflow, "Please prepare that same ticket again.")
        self.assertEqual(result["state"], "await_confirmation")
        self.assertNotEqual(result["pending_action"]["action_id"], pending["action_id"])
        self.assertEqual(self.mcp.writes, [])

    async def test_missing_facts_after_clarification_complete_the_requested_draft(self):
        await self.chat(self.workflow({"action": "retrieve"}), "My VPN shows NX-999. What should I do?")
        clarification = await self.chat(self.workflow(), "I have not tried anything yet. Please prepare a ticket.")
        self.assertEqual(clarification["state"], "clarification")
        self.assertEqual(self.store.get_session("s")["draft_pending"], "clarification")
        draft = {"intent": "draft", "subject": "NakhlaConnect NX-999", "description": "VPN shows NX-999.",
                 "attempted_steps": [], "affected_users": 1}
        workflow = self.workflow({"action": "retrieve"}, draft, {"accepted": True, "complete": True})
        result = await self.chat(workflow, "I can continue working without the VPN.")
        self.assertEqual(result["state"], "await_confirmation")
        self.assertEqual(self.store.get_session("s")["draft_pending"], "draft")

    async def test_switching_to_a_new_issue_does_not_inherit_draft_intent(self):
        await self.chat(self.workflow({"action": "retrieve"}), "My VPN shows NX-999. What should I do?")
        await self.chat(self.workflow(), "I have not tried anything yet. Please prepare a ticket.")
        self.assertEqual(self.store.get_session("s")["draft_pending"], "clarification")
        workflow = self.workflow({"action": "retrieve"}, ANSWER, {"accepted": True, "complete": True})
        result = await self.chat(workflow, "New issue: NakhlaID shows NID-423.")
        self.assertNotEqual(result["state"], "await_confirmation")
        self.assertIsNone(result["pending_action"])
        self.assertEqual(self.store.get_session("s")["draft_pending"], "")
        self.assertEqual(self.mcp.writes, [])

    def test_draft_signal_is_per_message(self):
        self.assertTrue(draft_signal("Please prepare a ticket."))
        self.assertIsNone(draft_signal(self.RECALL_QUESTION))
        self.assertFalse(requested_draft(self.RECALL_QUESTION))


if __name__ == "__main__":
    unittest.main()
