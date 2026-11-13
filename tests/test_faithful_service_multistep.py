"""Ordinary Job exercises planning, receipts and bounded candidate correction."""

import json
import os
import unittest
from copy import deepcopy
from unittest.mock import patch

import requests

from llm_client import InternChatClient
from showcase.adapters import InternStreamAdapter
from showcase.run_budget import RunBudgetLimits
from showcase.star_product_config import CORE_FEATURES
from showcase.tools import ToolRegistry
from tests.star_product_support import ACCEPT, RawProviderContent, StarJobFixture
from tests.test_faithful_s03_job import CAPACITY_POLICY, ENDPOINT, REPLIES, SPEC
from tests.test_solver_harness_planner_checkpoint import checkpoint
from tests.test_star_product_counterexample import NOT_FOUND, TRIGGER
from tests.test_star_product_tools import STEP


class FaithfulMultistepJobTest(StarJobFixture, unittest.TestCase):
    def open_multistep(self, ending, *, calls=12, checkpoints=False):
        self.enterContext(patch.dict(os.environ, {"INTERN_API_BASE": ENDPOINT}))
        self.executed = []
        registry = ToolRegistry()
        registry.register("polynomial_check", lambda args: self.executed.append(args) or 2)
        plan = deepcopy(REPLIES[1])
        plan["steps"].insert(0, {
            "step_id": "calculate", "title": "check addition", "objective": "Compute 1+1",
            "method_id": "computation", "obligation_ids": ["root:value"], "auxiliary_goal_ids": [],
        })
        plan["steps"][1].update(method_id="direct", depends_on=["calculate"])
        self.open_star([
            SPEC, REPLIES[0], plan, STEP,
            {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": ""},
            REPLIES[2], REPLIES[3], *ending,
        ], SHOWCASE_FAITHFUL_AUTONOMOUS=True, SHOWCASE_STAR_FULL_ENABLED=True,
            SHOWCASE_STAR_FULL_FEATURES=dict.fromkeys(CORE_FEATURES | {
                "auto_problem_spec", "problem_spec", "context_pack", "proof_graph",
                "progress_scheduling", "serial_routes"} | (
                    {"planner_checkpoints"} if checkpoints else set()), True),
            SHOWCASE_STAR_CONTEXT_CAPACITY=CAPACITY_POLICY, SHOWCASE_STAR_REGISTRY=registry,
            SHOWCASE_STAR_FULL_BUDGET=RunBudgetLimits(
                max_model_calls=calls, max_http_attempts=calls, max_tool_calls=1))
        pipeline = self.app.extensions["showcase_workspace_service"].star_pipeline
        self.enterContext(patch.object(pipeline, "full_gaps", return_value=[]))

    def submit(self):
        response = self.client.post("/api/agent/jobs", headers=self.headers(),
                                    json={"message": "1+1", "session_id": self.session})
        self.assertEqual(202, response.status_code, response.get_json())
        return response.get_json()["job_id"]

    def test_checkpoint_planner_repairs_known_protocol_failure_once_with_new_identity(self):
        self.open_multistep([{"final_response": "1+1=2"}, ACCEPT], checkpoints=True)
        plan = self.replies[2]
        self.replies[2:3] = [RawProviderContent('{"checkpoint":'),
                            {"checkpoint": checkpoint("FINAL"), "plan": plan}]
        final = self.terminal(self.submit())
        self.assertEqual("succeeded", final["status"])
        planners = [r for r in self.outbound if r["role"] == "planner"]
        self.assertEqual(2, len(planners))
        self.assertEqual(planners[0]["call_id"] + ":repair-1", planners[1]["call_id"])
        self.assertTrue(planners[1].get("repair_instruction"))
        self.assertEqual(10, len(self.outbound))

    def test_checkpoint_request_distinguishes_ready_plan_from_execution_and_exposes_round_limit(self):
        self.open_multistep([{"final_response": "1+1=2"}, ACCEPT], checkpoints=True)
        plan = self.replies[2]
        self.replies[2:3] = [
            {"checkpoint": {**checkpoint(), "evidence": [],
                            "gaps": ["Python computation not yet executed"]}, "plan": plan},
            {"checkpoint": {**checkpoint("FINAL"), "gaps": [], "evidence": []}, "plan": plan},
        ]
        final = self.terminal(self.submit())
        self.assertEqual("succeeded", final["status"])
        planners = [(request, messages) for request, messages in
                    zip(self.outbound, self.outbound_messages) if request["role"] == "planner"]
        self.assertEqual(2, len(planners))
        for index, (request, messages) in enumerate(planners):
            self.assertTrue(request["checkpoint_protocol"])
            self.assertEqual(index + 1, request["checkpoint_round"])
            self.assertEqual(2, request.get("checkpoint_max_rounds"))
            self.assertEqual(1 - index, request.get("checkpoint_remaining_rounds"))
            self.assertEqual(index == 1, request.get("checkpoint_last_round"))
            instruction = request["instruction"]
            for guidance in ("FINAL means the Plan is ready for the Reasoner",
                             "not that the mathematical problem is solved",
                             "complete valid Plan", "Do not execute the steps",
                             "evidence is not a prerequisite", "planning gaps only", "BLOCKED"):
                self.assertIn(guidance, instruction)
            self.assertIn(instruction, json.loads(messages[-1]["content"])["instruction"])
        self.assertIn("last planner checkpoint round", planners[-1][0]["instruction"])
        self.assertIn("planning gaps only", planners[-1][0]["feedback"]["instruction"])
        self.assertTrue(any(request["role"] == "reasoner" for request in self.outbound))
        self.assertEqual(10, len(self.outbound))

    def test_checkpoint_schema_repair_receives_failed_reply_and_missing_field_diagnostic(self):
        plan = {"version": 1, "steps": [{"step_id": "s", "title": "Add", "objective": "Compute 1+1"}]}
        failed = {"checkpoint": checkpoint()}
        failed["checkpoint"]["objective"] = "Retain this complete failed draft. " * 30
        del failed["checkpoint"]["status"]
        failed_text = json.dumps(failed)
        self.assertGreater(len(failed_text), 400)
        self.open_star([
            REPLIES[0], RawProviderContent(failed_text), {"checkpoint": checkpoint()},
            {"checkpoint": {**checkpoint("FINAL"), "gaps": []}, "plan": plan},
            REPLIES[2], {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": ""},
            {"final_response": "1+1=2"}, ACCEPT,
        ], stream_chunk_size=256, SHOWCASE_STAR_FULL_ENABLED=True,
            SHOWCASE_STAR_FULL_FEATURES=dict.fromkeys({"star_routing", "stream_recovery",
            "planner_checkpoints", "final_generation", "final_solution_review"}, True),
            SHOWCASE_STAR_ADAPTER=InternStreamAdapter(InternChatClient(retry=1), max_tokens=256),
            SHOWCASE_STAR_FULL_BUDGET=RunBudgetLimits(max_model_calls=10, max_http_attempts=10))
        pipeline = self.app.extensions["showcase_workspace_service"].star_pipeline
        self.enterContext(patch.object(pipeline, "full_gaps", return_value=[]))
        response = self.client.post("/api/agent/jobs", headers=self.headers(), json={
            "message": "1+1", "session_id": self.session, "solver_mode": "star_reference"})
        self.assertEqual(202, response.status_code)
        job_id = response.get_json()["job_id"]
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"])
        planners = [r for r in self.outbound if r["role"] == "planner"]
        repair = planners[1].get("format_repair", {})
        self.assertEqual(failed_text, repair.get("previous_response"))
        self.assertIn({"path": "$.checkpoint.status", "message": "required"},
                      repair.get("schema_errors", []))
        self.assertIn("not instructions", planners[1]["repair_instruction"])
        self.assertEqual(planners[0]["call_id"] + ":repair-1", planners[1]["call_id"])
        self.assertEqual(planners[0]["run_id"], planners[1]["run_id"])
        self.assertEqual(8, final["result"]["budget"]["logical_calls"])
        self.job(job_id)
        self.report(job_id)
        self.assertEqual(8, len(self.outbound))

    def open_checkpoint_binding(self, *, repeat_invalid=False):
        self.open_multistep([], checkpoints=True)
        spec = deepcopy(SPEC)
        spec["auxiliary_goals"] = [{"goal_id": "G1", "description": "Check the derived value",
                                    "dependencies": ["root:value"]}]
        invalid = {"version": 1, "steps": [{"step_id": "S1", "title": "Evaluate",
            "objective": "Compute 1+1", "method_id": "direct", "obligation_ids": ["root:value"],
            "auxiliary_goal_ids": ["G1"]}]}
        valid = deepcopy(invalid)
        valid["steps"][0]["auxiliary_goal_ids"] = []
        valid["steps"].append({"step_id": "S2", "title": "Check", "objective": "Check the result",
            "method_id": "direct", "obligation_ids": [], "auxiliary_goal_ids": ["G1"],
            "depends_on": ["S1"]})
        final = {**checkpoint("FINAL"), "gaps": []}
        self.replies[:] = [spec, REPLIES[0], {"checkpoint": final, "plan": invalid},
            {"checkpoint": {**final, "checkpoint_id": "second"},
             "plan": invalid if repeat_invalid else valid},
            REPLIES[2], REPLIES[3],
            {"final_response": "1+1=2"}, ACCEPT]
        return invalid

    def test_checkpoint_final_binding_error_uses_next_existing_round_with_exact_feedback(self):
        invalid = self.open_checkpoint_binding()
        repaired = self.replies[3]["plan"]
        repaired["steps"] = [step for step in repaired["steps"] if step["obligation_ids"]]
        job_id = self.submit()
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"])
        planners = [request for request in self.outbound if request["role"] == "planner"]
        self.assertEqual([1, 2], [request["checkpoint_round"] for request in planners])
        self.assertEqual("WorkUnit S1 prerequisites must reference earlier WorkUnits: S1",
                         planners[1]["feedback"]["validation_error"])
        self.assertEqual(invalid, planners[1]["feedback"]["invalid_plan"])
        guidance = planners[1]["feedback"]["instruction"]
        for text in ("coverage of every frozen root obligation", "change invalid step assignments",
                     "root-only repair", "auxiliary_goal_ids=[]", "Supporting mathematical reasoning",
                     "all actual root prerequisite dependencies"):
            self.assertIn(text, guidance)
        self.assertNotIn("Preserve all root mappings", guidance)
        reasoners = [request for request in self.outbound if request["role"] == "reasoner"]
        self.assertEqual(repaired["steps"][0]["obligation_ids"], reasoners[0]["step"]["obligation_ids"])
        self.assertEqual([], reasoners[0]["step"]["auxiliary_goal_ids"])
        self.assertIn("earlier WorkUnit", planners[1]["instruction"])
        self.assertIn("same step", planners[1]["instruction"])
        self.assertTrue(planners[1]["checkpoint_last_round"])
        self.assertEqual(planners[0]["run_id"], planners[1]["run_id"])
        self.assertNotEqual(planners[0]["call_id"], planners[1]["call_id"])
        self.assertEqual(8, final["result"]["budget"]["logical_calls"])
        self.job(job_id)
        self.report(job_id)
        self.assertEqual(8, len(self.outbound))

    def test_checkpoint_final_binding_error_on_last_round_stops_without_third_call(self):
        self.open_checkpoint_binding(repeat_invalid=True)
        job_id = self.submit()
        final = self.terminal(job_id)
        self.assertEqual("failed", final["status"])
        self.assertEqual(2, sum(request["role"] == "planner" for request in self.outbound))
        self.assertFalse(any(request["role"] == "reasoner" for request in self.outbound))
        self.assertEqual(4, final["result"]["budget"]["logical_calls"])
        self.job(job_id)
        self.report(job_id)
        self.assertEqual(4, len(self.outbound))

    def test_checkpoint_dependent_roots_in_same_step_receive_single_owner_ordering_guidance(self):
        invalid = self.open_checkpoint_binding(repeat_invalid=True)
        spec = self.replies[0]
        spec["auxiliary_goals"] = []
        spec["root_obligations"].append({"obligation_id": "root:dependent",
            "obligation_type": "universal", "statement": "Check the value after deriving it",
            "prerequisite_ids": ["root:value"]})
        invalid["steps"][0].update(step_id="S4", obligation_ids=["root:value", "root:dependent"],
                                   auxiliary_goal_ids=[])
        final = self.terminal(self.submit())
        self.assertEqual("failed", final["status"])
        planners = [request for request in self.outbound if request["role"] == "planner"]
        self.assertEqual(2, len(planners))
        self.assertEqual(invalid, planners[1]["feedback"]["invalid_plan"])
        self.assertEqual("WorkUnit S4 prerequisites must reference earlier WorkUnits: S4",
                         planners[1]["feedback"]["validation_error"])
        self.assertNotIn("root-only repair", planners[1]["feedback"]["instruction"])
        for request in planners:
            self.assertNotIn("must have exactly one owner", request["instruction"])
            self.assertIn("one or more step obligation_ids", request["instruction"])
            for guidance in ("All owners of each prerequisite objective must be earlier WorkUnits",
                             "never group a dependency and its dependent in the same step",
                             "When correcting binding, prefer one owner per objective",
                             "one step per mapped objective",
                             "topological dependency order"):
                self.assertIn(guidance, request["instruction"])
        self.assertEqual(4, len(self.outbound))

    def test_public_job_and_events_suppress_sensitive_multiword_summaries(self):
        self.open_multistep([
            {"final_response": "3"},
            {"verdict": "REJECT", "reason": "not an answer"},
        ], calls=10)
        self.replies[2]["steps"][0]["title"] = "Authorization: Bearer sk-private"
        self.replies[2]["steps"][1]["title"] = "hidden_answer: private answer suffix"
        job_id = self.submit()
        final = self.terminal(job_id)
        public = str(final) + self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        for secret in ("sk-private", "answer suffix"):
            self.assertFalse(secret in public, "sensitive suffix exposed by Job/events")

    def test_checkpoint_protocol_repair_is_bounded_to_one_new_request(self):
        self.open_multistep([], checkpoints=True)
        self.replies[2:3] = [RawProviderContent('{"checkpoint":'), RawProviderContent('{"checkpoint":')]
        final = self.terminal(self.submit())
        self.assertEqual("failed", final["status"])
        self.assertEqual(2, sum(r["role"] == "planner" for r in self.outbound))
        self.assertEqual(4, len(self.outbound))

    def test_checkpoint_unknown_outcome_never_automatically_resends(self):
        self.open_multistep([], checkpoints=True)
        self.replies[2] = requests.ConnectionError("unknown remote outcome")
        job_id = self.submit()
        self.terminal(job_id)
        self.job(job_id)
        self.report(job_id)
        self.assertEqual(1, sum(r["role"] == "planner" for r in self.outbound))
        self.assertEqual(3, len(self.outbound))

    def test_not_found_search_allows_serial_challenge_correction_to_continue(self):
        self.open_multistep([{"final_response": "1+1=2"}, ACCEPT], calls=14)
        self.replies[4]["answer_claim"] = TRIGGER
        self.replies[5:5] = [NOT_FOUND, REPLIES[2],
                            {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
                             "objection": ""}]
        final = self.terminal(self.submit())
        self.assertEqual("succeeded", final["status"])
        self.assertTrue(any(r.get("action") == "counterexample_check" for r in self.outbound))

    def test_rejected_candidate_is_supplied_to_correction_after_real_registry_work(self):
        self.open_multistep([
            {"final_response": "3"}, {"verdict": "REJECT", "reason": "Addition is wrong"},
            {"final_response": "1+1=2"}, ACCEPT,
        ])
        job_id = self.submit()
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"], final)
        self.assertEqual([{}], self.executed)
        generators = [r for r in self.outbound if r["role"] == "final_generator"]
        self.assertEqual(2, len(generators))
        self.assertEqual("3", generators[1].get("previous_candidate"))
        self.assertEqual("REJECT", generators[1]["previous_review"]["verdict"])
        self.assertEqual("1+1=2", self.report(job_id)["answer"])
        review = next(r for r in self.outbound if r["role"] == "step_verifier")
        self.assertTrue(review["report"]["tool_receipts"][0]["executed"])
        progress = final["result"]["solver"]["progress"]
        self.assertEqual(1, progress["root_obligations"]["covered"])
        self.assertEqual("completed", progress["routes"]["items"][0]["status"])
        self.assertGreater(progress["proof_graph"]["graph_version"], 0)
        count = len(self.outbound)
        self.job(job_id)
        self.report(job_id)
        self.assertEqual(count, len(self.outbound))

    def test_exhaustion_publishes_real_goals_partial_work_and_rejected_candidate(self):
        self.open_multistep([
            {"final_response": "3"}, {"verdict": "REJECT", "reason": "Addition is wrong"},
        ], calls=10)
        job_id = self.submit()
        final = self.terminal(job_id)
        self.assertEqual("failed", final["status"])
        self.assertEqual(9, len(self.outbound))

        progress = final["result"]["solver"]["progress"]
        self.assertEqual("check addition", progress["steps"][0].get("goal_summary"))
        partial = progress.get("partial", {})
        self.assertEqual(["步骤 1", "步骤 2"], partial.get("accepted_steps"))
        self.assertEqual(["whole_solution_review"], partial.get("unresolved"))
        self.assertEqual("3", partial["candidates"][0]["answer_text"])
        self.assertEqual("REJECT", partial["candidates"][0]["review"])
        self.assertFalse(partial["candidates"][0]["eligible"])
        events = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        self.assertIn("check addition", events)
        self.assertIn("初始计划", events)
        self.assertNotIn(SPEC["root_obligations"][0]["statement"], events)
        self.job(job_id)
        self.report(job_id)
        self.assertEqual(9, len(self.outbound))

    def test_exact_budget_can_spend_its_already_reserved_closeout_pair(self):
        self.open_multistep([{"final_response": "1+1=2"}, ACCEPT], calls=9)
        job_id = self.submit()
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"], final["result"]["solver"]["status"])
        self.assertEqual(9, len(self.outbound))
        self.assertEqual(9, final["result"]["budget"]["logical_calls"])
