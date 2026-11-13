"""Native checkpoint requests fit the action reserved by ordinary submission."""

import threading
import unittest
from copy import deepcopy
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import InternModelAdapter
from showcase.run_budget import RunBudgetLimits
from showcase.star_product_config import CORE_FEATURES
from showcase.tools import ToolRegistry
from tests.star_product_support import StarJobFixture
from tests.test_solver_harness_planner_checkpoint import checkpoint as planner_checkpoint
from tests.test_solver_harness_reasoner_checkpoint import checkpoint as reasoner_checkpoint
from tests.test_star_population_runtime import CAPACITY, PROBLEM, ROOT_ID, SPEC


class NativePopulationBudgetTest(StarJobFixture, unittest.TestCase):
    def test_plain_checkpoint_routes_reach_http_and_deliver_under_original_budget(self):
        self.run_checkpoint_routes()

    def test_checkpoint_local_precheck_uses_original_root_tool_budget(self):
        self.run_checkpoint_routes(use_tool=True)

    def run_checkpoint_routes(self, *, use_tool=False):
        """Exercise ordinary admission and real adapter serialization with offline HTTP."""
        entered = threading.Barrier(2)
        concurrent = []
        executed = []
        registry = ToolRegistry()
        registry.register("polynomial_check", lambda args: executed.append(args) or 2)

        def provider(request):
            role = request["role"]
            if role == "problem_intake":
                return deepcopy(SPEC)
            if role == "explore":
                return {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []}
            if role == "planner":
                plan = {"version": 1, "steps": [{
                    "step_id": "direct", "title": "Direct", "objective": PROBLEM,
                    "method_id": "direct", "obligation_ids": [ROOT_ID],
                    "auxiliary_goal_ids": [],
                }]}
                alternative = deepcopy(plan)
                alternative["steps"][0].update(step_id="construction", method_id="construction")
                return {"checkpoint": {**planner_checkpoint("FINAL"), "gaps": []},
                        "plan": {**plan, "alternative_plans": [alternative],
                                 "execution_selection": {"mode": "population",
                                                         "reason": "Independent complete routes."}}}
            if role == "reasoner":
                entered.wait(timeout=5)
                concurrent.append(request)
                reply = reasoner_checkpoint("FINAL", marker=request["step"]["step_id"])
                reply["checkpoint"].update(objective=request["current_goal"], argument="1+1=2",
                    claims=[{"statement": "1+1=2", "label": "verified"}])
                if use_tool:
                    reply["checkpoint"]["claims"][0].update(label="easy-verify", tool_request={
                        "tool": "polynomial_check", "arguments": {}, "scope": "finite_computation"})
                return reply
            if role == "step_verifier":
                if use_tool:
                    self.assertEqual("success", request["report"]["tool_receipts"][0]["status"])
                return {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
                        "objection": "", "obligation_evidence": [{
                            "obligation_id": ROOT_ID, "evidence_category": "format_check",
                            "claim_indexes": [0]}]}
            if role == "final_generator":
                return {"final_response": "1+1=2"}
            if role == "whole_solution_verifier":
                return {"verdict": "ACCEPT", "reason": "Complete answer."}
            raise AssertionError(role)

        limits = RunBudgetLimits(max_model_calls=48, max_http_attempts=48, max_tool_calls=8,
                                 max_tokens=2_097_152, max_runtime_seconds=2400)
        self.open_star([provider] * 48,
            SHOWCASE_STAR_ADAPTER=InternModelAdapter(InternChatClient(retry=1, timeout=180),
                                                   max_tokens=32768),
            SHOWCASE_FAITHFUL_AUTONOMOUS=True, SHOWCASE_STAR_FULL_ENABLED=True,
            SHOWCASE_STAR_FULL_FEATURES=dict.fromkeys(CORE_FEATURES | {
                "auto_problem_spec", "problem_spec", "proof_graph", "progress_scheduling",
                "serial_routes", "planner_checkpoints", "reasoner_checkpoints"}, True),
            SHOWCASE_STAR_FULL_BUDGET=limits, SHOWCASE_STAR_POPULATION_ENABLED=True,
            SHOWCASE_STAR_POPULATION_CAPACITY=CAPACITY,
            SHOWCASE_STAR_REGISTRY=registry,
            SHOWCASE_STAR_POPULATION_REQUEST_TIMEOUT_SECONDS=180)
        pipeline = self.app.extensions["showcase_workspace_service"].star_pipeline
        with patch.object(pipeline, "full_gaps", return_value=[]):
            response = self.client.post("/api/agent/jobs", headers=self.headers(),
                json={"message": PROBLEM, "session_id": self.session})
            self.assertEqual(202, response.status_code, response.get_json())
            job_id = response.get_json()["job_id"]
            final = self.terminal(job_id, timeout=20)
        solver = final["result"]["solver"]
        self.assertEqual("population", solver["execution_selection"]["selected"])
        self.assertEqual(2, len(concurrent), {
            "outbound_roles": [item["role"] for item in self.outbound],
            "recovery": solver.get("recovery"), "population": solver.get("population")})
        self.assertTrue(all(item["checkpoint_protocol"] for item in concurrent))
        self.assertEqual(2, len({item["call_id"] for item in concurrent}))
        self.assertEqual("succeeded", final["status"])
        self.assertEqual("1+1=2", final["result"]["final_response"])
        budget = final["result"]["budget"]
        self.assertEqual(48, budget["limits"]["max_model_calls"])
        self.assertEqual(48, budget["limits"]["max_http_attempts"])
        self.assertEqual(8, budget["limits"]["max_tool_calls"])
        self.assertEqual(2_097_152, budget["limits"]["max_tokens"])
        self.assertEqual(2400, budget["limits"]["max_runtime_seconds"])
        self.assertEqual(solver["execution_selection"]["budget"]["deadline_at"], budget["deadline_at"])
        self.assertEqual(len(self.outbound), budget["logical_calls"])
        self.assertEqual(len(self.outbound), budget["http_attempts"])
        self.assertEqual(2 if use_tool else 0, len(executed))
        self.assertEqual(len(executed), budget["tool_calls"])
        self.assertEqual("same_artifact", self.report(job_id)["semantics"]["binding"])
