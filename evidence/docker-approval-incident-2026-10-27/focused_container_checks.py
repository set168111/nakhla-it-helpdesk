"""Container-only focused regressions; fake external calls and temporary state."""
import os,socket,sys,unittest,json
from unittest.mock import patch
sys.path.insert(0,"/workspace")
sys.path.insert(0,"/tmp/helpdesk-focused-tests")
os.environ["OPENROUTER_API_KEY"]=""
os.environ["LIVE_KIT_TEST"]="0"
os.environ["LIVE_FAILURE_TEST"]="0"
from test_approvals import ApprovalTests
from test_agent_workflow import WorkflowTests
names=[
 (ApprovalTests,"test_incident_activated_after_draft_supersedes_without_write"),
 (ApprovalTests,"test_incident_during_unknown_recovery_preserves_duplicate_write_guard"),
 (ApprovalTests,"test_concurrent_double_approval_one_write"),
 (ApprovalTests,"test_unknown_retry_retains_payload_and_key"),
 (ApprovalTests,"test_unknown_retry_changed_evidence_retains_unknown"),
 (ApprovalTests,"test_payload_tampering_cannot_commit"),
 (ApprovalTests,"test_expired_draft_cannot_commit"),
 (ApprovalTests,"test_restart_session_and_unknown_recovery"),
 (WorkflowTests,"test_truncated_issue_retains_documented_code_for_later_incident"),
 (WorkflowTests,"test_active_incident_matches_gateway_and_blocks_duplicate")]
def deny(*args,**kwargs):raise AssertionError("Network prohibited in focused mocked regressions")
with patch.object(socket.socket,"connect",deny),patch("socket.create_connection",deny):
 result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(cls(name) for cls,name in names))
print(json.dumps({"kind":"focused existing tests inside app container","tests_run":result.testsRun,"passed":result.wasSuccessful(),"failures":len(result.failures),"errors":len(result.errors),"skipped":len(result.skipped),"external_network":"blocked by harness","state":"TemporaryDirectory per test; working data untouched","real_ticket_writes":0}))
sys.exit(0 if result.wasSuccessful() else 1)
