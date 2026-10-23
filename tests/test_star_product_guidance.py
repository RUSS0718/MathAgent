"""Actual blocked/tool failures drive bounded Guidance through public Jobs."""

import json
import tempfile
import unittest
from unittest.mock import patch

import requests

from showcase.python_executor import DockerPythonExecutor
from showcase.run_budget import RunBudgetLimits
from showcase.tools import ToolRegistry
from tests.star_product_support import ACCEPT, StarJobFixture
from tests.test_star_product_tools import FEATURES, NEED_PLAN, PLAN, STEP, VERDICT

PLAIN = {"argument": "Addition", "claims": [], "blocked": False}
PLAN_WITH_TWO = {"version": 1, "steps": [
    {"step_id": "s1", "title": "Establish fact", "objective": "derive a reusable fact"},
    {"step_id": "s2", "title": "Apply fact", "objective": "use the reusable fact", "depends_on": ["s1"]},
]}
GUIDANCE = {"action_type": "retry_different_method", "specific_task": "USE_ADDITION_SENTINEL",
            "use_pure_reasoning": True, "trace_back_to": None, "rationale": "Avoid blocked method"}
PLAN_V2 = {"version": 2, "steps": [{"step_id": "sum2", "title": "Add", "objective": "Compute 1+1"}]}
REUSED_PLAN_V2 = {"version": 2, "steps": [{"step_id": "sum", "title": "Add", "objective": "Compute 1+1"}]}
CHALLENGE_VERDICT = {**VERDICT, "verdict": "CHALLENGE", "logic_gate": "FAIL",
                     "objection": "Check the boundary case"}
DELEGATE_TWO = {"tasks": [
    {"prompt": "Find a short addition argument", "permitted_tools": [], "timeout_seconds": 2},
    {"prompt": "Check boundary cases without code", "permitted_tools": [], "timeout_seconds": 2},
]}
CONTINUE_WITH_OLD_DIRECTION = {
    "decision": "CONTINUE", "reason_summary": "Try one fresh attempt", "plan_summary": "Add",
    "forbidden_directions": ["STALE_DIRECTION"],
    "reusable_results": ["RESCUE_SENTINEL"], "trace_back_to": None,
}


def guidance(action, *, trace_back_to=None):
    return {"action_type": action, "specific_task": f"DO_{action.upper()}",
            "use_pure_reasoning": False, "trace_back_to": trace_back_to,
            "rationale": "Use a bounded local recovery"}


class StarGuidanceTest(StarJobFixture, unittest.TestCase):
    def protocols_from(self, request):
        messages = self.outbound_messages[self.outbound.index(request)]
        layer = next(
            json.loads(message["content"])
            for message in messages
            if '"kind": "protocols"' in message["content"]
        )
        return layer["protocols"]

    def protocol_from(self, request, protocol_id):
        protocol = next(
            item for item in self.protocols_from(request) if item["id"] == protocol_id
        )
        self.assertEqual("1", protocol["version"])
        self.assertTrue(protocol["instructions"].strip())
        self.assertTrue(protocol["trigger"].strip())
        self.assertTrue(protocol["permissions"])
        return protocol

    def run_public(self, replies, **config):
        registry = config.pop("SHOWCASE_STAR_REGISTRY", None)
        budget = config.pop("SHOWCASE_STAR_BUDGET", None)
        features = config.pop("SHOWCASE_STAR_FEATURES", {})
        if registry is None:
            registry = ToolRegistry()
            registry.register("polynomial_check", lambda _args: None)
        self.open_star(replies, SHOWCASE_STAR_FEATURES={
                **FEATURES, "meta_guidance": True, "skills": True, **features,
            },
            SHOWCASE_STAR_BUDGET=budget or RunBudgetLimits(
                max_model_calls=18, max_http_attempts=18
            ),
            SHOWCASE_STAR_REGISTRY=registry, **config)
        job_id = self.create_job()
        job = self.terminal(job_id)
        stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        events = [json.loads(line[6:]) for line in stream.splitlines() if line.startswith("data: ")]
        return job_id, job, events

    def test_blocked_step_guidance_changes_next_actual_task_and_pure_reasoning(self):
        job_id, job, events = self.run_public([
            NEED_PLAN, PLAN, {**PLAIN, "blocked": True}, GUIDANCE,
            STEP, VERDICT, {"final_response": "2"}, ACCEPT,
        ])
        self.assertEqual("succeeded", job["status"], job)
        meta = next(r for r in self.outbound if r["role"] == "meta")
        self.assertEqual("stuck", meta["guidance_request"]["failure_type"])
        retry = next(r for r in self.outbound if r["role"] == "reason_noncoding")
        self.assertEqual("USE_ADDITION_SENTINEL", retry["specific_task"])
        self.assertNotIn("python_math", retry["allowed_tools"])
        self.assertEqual(0, self.report(job_id)["budget"]["tool_calls"])
        receipt = job["result"]["tool_results"][0]["receipt"]
        self.assertEqual("pure_reasoning_denied", receipt["reason"])
        decided = next(e for e in events if e.get("solver_event_type") == "meta_guidance_decided")
        self.assertEqual("retry_different_method", decided.get("action_type"))
        self.assertEqual("stuck", decided.get("failure_type"))
        self.assertTrue(decided.get("use_pure_reasoning"))
        self.assertIn("meta-intervention-protocol", decided["active_skill_ids"])
        self.assertIn("math-solving-strategies", decided["active_skill_ids"])
        self.assertEqual("1", decided["skill_protocol_version"])
        public_protocol = next(
            item for item in decided["skill_protocols"]
            if item["id"] == "meta-intervention-protocol"
        )
        self.assertEqual("meta role", public_protocol["trigger"])
        self.assertEqual(["read_state", "read_ledger"], public_protocol["permissions"])
        self.assertNotIn("instructions", public_protocol)
        protocol_layer = self.protocols_from(meta)
        self.assertIn(
            "meta-intervention-protocol",
            [item["id"] for item in protocol_layer],
        )
        intervention = next(
            item for item in protocol_layer
            if item["id"] == "meta-intervention-protocol"
        )
        self.assertEqual("1", intervention["version"])
        self.assertEqual("meta role", intervention["trigger"])
        self.assertIn("Choose one strategy decision", intervention["instructions"])
        self.assertEqual(["read_state", "read_ledger"], intervention["permissions"])
        strategy = next(
            item for item in protocol_layer
            if item["id"] == "math-solving-strategies"
        )
        self.assertEqual("1", strategy["version"])
        self.assertEqual("meta selects mathematical method", strategy["trigger"])
        self.assertEqual(["read_ledger"], strategy["permissions"])
        self.assertTrue(strategy["instructions"].strip())
        self.assertEqual("fault_injection", job["result"]["evidence_kind"])
        self.assertTrue(any(e.get("solver_event_type") == "meta_guidance_applied" for e in events))
        self.assertNotIn("USE_ADDITION_SENTINEL", json.dumps(events))
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        self.assertTrue(any(e.get("solver_event_type") == "meta_guidance_applied" for e in evidence["timeline"]))
        self.assertNotIn("USE_ADDITION_SENTINEL", json.dumps(self.report(job_id), ensure_ascii=False))
        self.assertNotIn("USE_ADDITION_SENTINEL", json.dumps(evidence, ensure_ascii=False))
        evidence_decision = next(
            item for item in evidence["timeline"]
            if item.get("solver_event_type") == "meta_guidance_decided"
        )
        self.assertIn("skill_protocols", evidence_decision)
        self.assertEqual(decided["skill_protocols"], evidence_decision["skill_protocols"])
        self.assertNotIn("instructions", json.dumps(evidence_decision, ensure_ascii=False))

    def test_each_valid_guidance_action_runs_through_public_job(self):
        cases = [
            ("explore_more", [{"assessment": "PARTIALLY_SOLVED", "worked": ["bounded case"],
                               "failed": [], "candidates": []}, STEP, VERDICT,
                              {"final_response": "2"}, ACCEPT], "explore", "DO_EXPLORE_MORE"),
            ("trace_back", [STEP, VERDICT, {"final_response": "2"}, ACCEPT],
             "reasoner", "DO_TRACE_BACK"),
            ("replan", [PLAN_V2, STEP, VERDICT, {"final_response": "2"}, ACCEPT],
             "planner", "DO_REPLAN"),
        ]
        for action, tail, role, task in cases:
            with self.subTest(action=action):
                job_id, job, events = self.run_public([
                    NEED_PLAN, PLAN, {**PLAIN, "blocked": True},
                    guidance(action, trace_back_to=1 if action == "trace_back" else None),
                    *tail,
                ])
                self.assertEqual("succeeded", job["status"], job)
                request = next(item for item in self.outbound if item["role"] == role and (
                    item.get("specific_task") == task
                ))
                self.assertEqual(task, request["specific_task"])
                if action == "explore_more":
                    request_index = self.outbound.index(request)
                    projection = next(
                        json.loads(message["content"])
                        for message in self.outbound_messages[request_index]
                        if '"kind": "projection"' in message["content"]
                    )
                    findings = projection["state"]["exploration_findings"]
                    self.assertEqual("unverified_exploration", findings[-1]["provenance"])
                applied = [event for event in events
                           if event.get("solver_event_type") in {
                               "meta_guidance_applied", "trace_back_applied", "plan_replaced"
                           }]
                self.assertTrue(any(event.get("action_type") == action for event in applied), applied)
                if action == "trace_back":
                    trace = next(event for event in applied
                                 if event.get("solver_event_type") == "trace_back_applied")
                    self.assertEqual("meta_guidance", trace["triggered_by"])
                    self.assertEqual("meta", trace["role"])
                    evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
                    evidence_trace = next(
                        event for event in evidence["timeline"]
                        if event.get("solver_event_type") == "trace_back_applied"
                    )
                    self.assertEqual(trace["active_skill_ids"], evidence_trace["active_skill_ids"])

    def test_known_managed_tool_failure_triggers_code_issue_protocol(self):
        registry = ToolRegistry()
        with tempfile.TemporaryDirectory() as artifact_root:
            registry.register_container_python(DockerPythonExecutor(
                image="sha256:" + "4" * 64, artifact_root=artifact_root))
            self.enterContext(patch("subprocess.run", side_effect=FileNotFoundError("docker absent")))
            step = {"argument": "Addition", "blocked": False, "claims": [{
                "statement": "2", "label": "easy-verify", "tool_request": {
                    "tool": "python_math", "arguments": {"code": "print(2)"},
                    "scope": "finite_computation", "expected_output": "2"}}]}
            job_id, job, events = self.run_public([
                NEED_PLAN, PLAN, step, guidance("retry_different_method"),
                STEP, VERDICT, {"final_response": "2"}, ACCEPT,
            ], SHOWCASE_STAR_REGISTRY=registry)
        self.assertEqual("succeeded", job["status"], job)
        meta = next(item for item in self.outbound if item["role"] == "meta")
        self.assertEqual("code_issue", meta["guidance_request"]["failure_type"])
        self.assertEqual("execution_error", meta["tool_failure"])
        decided = next(event for event in events
                       if event.get("solver_event_type") == "meta_guidance_decided")
        self.assertIn("code-issue-resolution", decided["active_skill_ids"])
        self.assertEqual("code_issue", decided["failure_type"])
        code_protocol = self.protocol_from(meta, "code-issue-resolution")
        self.assertEqual("1", code_protocol["version"])
        self.assertEqual("recorded timeout, execution error or output mismatch",
                         code_protocol["trigger"])
        self.assertIn("Reduce work for timeout", code_protocol["instructions"])
        self.assertEqual(["read_state"], code_protocol["permissions"])

    def test_known_terminated_managed_timeout_triggers_timeout_guidance(self):
        def known_timeout(executor, code, *, run_id, call_id, input_payload=None, canceled=None):
            store = executor.artifacts
            outcome = {
                "status": "timeout", "executed": True, "cleanup_verified": True,
                "unknown_outcome": False, "timeout": True, "exit_code": 124,
                "stdout": "", "stderr": "",
            }
            outcome["code_ref"] = store.put(
                run_id, call_id, "code", code.encode("utf-8"), media_type="text/x-python")
            outcome["input_ref"] = store.put(
                run_id, call_id, "input", json.dumps(input_payload).encode("utf-8"),
                media_type="application/json")
            outcome["stdout_ref"] = store.put(run_id, call_id, "stdout", b"")
            outcome["stderr_ref"] = store.put(run_id, call_id, "stderr", b"")
            outcome["receipt_ref"] = store.receipt(run_id, call_id, outcome)
            return outcome

        with tempfile.TemporaryDirectory() as artifact_root:
            registry = ToolRegistry()
            registry.register_container_python(DockerPythonExecutor(
                image="sha256:" + "5" * 64, artifact_root=artifact_root))
            self.enterContext(patch.object(DockerPythonExecutor, "execute", known_timeout))
            step = {"argument": "Addition", "blocked": False, "claims": [{
                "statement": "2", "label": "easy-verify", "tool_request": {
                    "tool": "python_math", "arguments": {"code": "print(2)"},
                    "scope": "finite_computation", "expected_output": "2"}}]}
            job_id, job, _events = self.run_public([
                NEED_PLAN, PLAN, step, guidance("retry_different_method"),
                STEP, VERDICT, {"final_response": "2"}, ACCEPT,
            ], SHOWCASE_STAR_REGISTRY=registry)
        self.assertEqual("succeeded", job["status"], job)
        meta = next(item for item in self.outbound if item["role"] == "meta")
        self.assertEqual("timeout", meta["guidance_request"]["failure_type"])
        timeout_receipt = job["result"]["tool_results"][0]["receipt"]
        self.assertEqual("timeout", timeout_receipt["status"])
        self.assertFalse(timeout_receipt["unknown_outcome"])

    def test_old_tool_failure_does_not_guide_reused_step_in_new_plan(self):
        with tempfile.TemporaryDirectory() as artifact_root:
            registry = ToolRegistry()
            registry.register_container_python(DockerPythonExecutor(
                image="sha256:" + "6" * 64, artifact_root=artifact_root))
            self.enterContext(patch("subprocess.run", side_effect=FileNotFoundError("docker absent")))
            failed_step = {"argument": "Addition", "blocked": False, "claims": [{
                "statement": "2", "label": "easy-verify", "tool_request": {
                    "tool": "python_math", "arguments": {"code": "print(2)"},
                    "scope": "finite_computation", "expected_output": "2"}}]}
            job_id, job, _events = self.run_public([
                NEED_PLAN, PLAN, failed_step, guidance("replan"),
                REUSED_PLAN_V2,
                PLAIN, VERDICT, {"final_response": "2"}, ACCEPT,
            ], SHOWCASE_STAR_REGISTRY=registry)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual(1, len([item for item in self.outbound if item["role"] == "meta"]))
        self.assertTrue(any(
            item["role"] == "planner" and item.get("plan_version") == 2
            for item in self.outbound
        ))

    def test_unknown_remote_timeout_stays_needs_review_without_meta_retry(self):
        registry = ToolRegistry()
        registry.register("polynomial_check", lambda _args: None)
        self.open_star([
            NEED_PLAN, PLAN, requests.Timeout("provider outcome unknown"),
        ], SHOWCASE_STAR_FEATURES={**FEATURES, "meta_guidance": True, "skills": True},
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=18, max_http_attempts=18),
            SHOWCASE_STAR_REGISTRY=registry)
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("failed", job["status"], job)
        self.assertEqual("interrupted", job["result"]["solver"]["status"])
        self.assertEqual(["explore", "planner", "reasoner"], [item["role"] for item in self.outbound])
        self.assertEqual(3, len(self.post.call_args_list))
        self.assertGreater(job["result"]["budget"]["unknown_attempts"], 0)

    def test_guidance_feature_disabled_keeps_the_existing_request_path(self):
        job_id, job, _events = self.run_public([
            NEED_PLAN, PLAN, {**PLAIN, "blocked": True}, VERDICT,
            {"final_response": "2"}, ACCEPT,
        ], SHOWCASE_STAR_FEATURES={"meta_guidance": False})
        self.assertEqual("succeeded", job["status"], job)
        self.assertNotIn("meta", [item["role"] for item in self.outbound])
        self.assertEqual(6, len(self.outbound))

    def test_skills_disabled_does_not_change_challenge_context(self):
        job_id, job, _events = self.run_public([
            NEED_PLAN, PLAN, STEP, CHALLENGE_VERDICT, PLAIN, VERDICT,
            {"final_response": "2"}, ACCEPT,
        ], SHOWCASE_STAR_FEATURES={"meta_guidance": False, "skills": False})
        self.assertEqual("succeeded", job["status"], job)
        challenge = next(item for item in self.outbound
                         if item["role"] == "reasoner" and item.get("round") == 1)
        messages = self.outbound_messages[self.outbound.index(challenge)]
        context = json.loads(messages[-1]["content"])
        self.assertNotIn("suspected_false_claim", context)
        self.assertNotIn("exploration_findings", context.get("role_context", {}).get("state", {}))
        self.assertNotIn("active_skill_ids", context)

    def test_multiple_research_tasks_are_bounded_and_used_by_replacement_plan(self):
        features = {"reexplore_after_replan": True}
        job_id, job, _events = self.run_public([
            NEED_PLAN, PLAN, {**PLAIN, "blocked": True}, guidance("replan"), DELEGATE_TWO,
            {"findings": ["RESEARCH_FINDING_A"]},
            {"findings": ["RESEARCH_FINDING_B"]},
            PLAN_V2, PLAIN, VERDICT, {"final_response": "2"}, ACCEPT,
        ], SHOWCASE_STAR_FEATURES=features)
        self.assertEqual("succeeded", job["status"], job)
        research = [item for item in self.outbound if item["role"] == "researcher"]
        self.assertEqual(2, len(research))
        self.assertTrue(all(item["run_id"] == job_id and item["allowed_tools"] == []
                            and item["tool_policy"]["allow"] == [] for item in research), research)
        planner = next(item for item in self.outbound
                       if item["role"] == "planner" and item.get("plan_version") == 2)
        findings = planner["reexploration_findings"]
        self.assertEqual({"RESEARCH_FINDING_A", "RESEARCH_FINDING_B"},
                         {item for finding in findings for item in finding["output"]["findings"]})
        self.assertTrue(all(finding["provenance"] == "unverified_exploration"
                            for finding in findings))
        meta_requests = [item for item in self.outbound if item["role"] == "meta"]
        self.assertEqual(2, len(meta_requests))
        self.assertEqual(meta_requests[0]["session_key"], meta_requests[1]["session_key"])
        self.assertEqual(1, len(meta_requests[1]["session_history"]))
        self.assertEqual("meta", meta_requests[1]["session_history"][0]["request"]["role"])
        self.assertEqual([], meta_requests[1]["forbidden_directions"])

    def test_guidance_replan_research_does_not_reuse_stale_meta_directions(self):
        replies = [
            NEED_PLAN, PLAN_WITH_TWO,
            {"argument": "RESCUE_SENTINEL", "claims": [], "blocked": False}, VERDICT,
            PLAIN, CHALLENGE_VERDICT, PLAIN, CHALLENGE_VERDICT,
            PLAIN, CHALLENGE_VERDICT, PLAIN, CHALLENGE_VERDICT,
            CONTINUE_WITH_OLD_DIRECTION,
            {**PLAIN, "blocked": True}, guidance("replan"),
            {"tasks": [{"prompt": "Find an alternative derivation",
                        "permitted_tools": [], "timeout_seconds": 2}]},
            {"findings": ["ALTERNATE_DERIVATION"]},
            PLAN_V2, PLAIN, VERDICT, {"final_response": "2"}, ACCEPT,
        ]
        job_id, job, _events = self.run_public(
            replies,
            SHOWCASE_STAR_FEATURES={"reexplore_after_replan": True},
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=24, max_http_attempts=24),
        )
        self.assertEqual("succeeded", job["status"], job)
        research_delegate = next(
            item for item in self.outbound
            if item["role"] == "meta" and item.get("action") == "delegate_research_task"
        )
        self.assertEqual(job_id, research_delegate["run_id"])
        self.assertEqual([], research_delegate["forbidden_directions"])
        planner = next(
            item for item in self.outbound
            if item["role"] == "planner" and item.get("plan_version") == 2
        )
        self.assertEqual([], planner["accepted_results"])
        self.assertEqual([], planner["rescued_results"])
        self.assertEqual(
            ["RESCUE_SENTINEL"],
            [item["statement"] for item in planner["failure_records"][-1]["invalidated_results"]],
        )


if __name__ == "__main__":
    unittest.main()
