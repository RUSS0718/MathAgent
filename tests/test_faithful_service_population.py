"""Ordinary submission selects actual routes under the original Job budget."""

import threading
import unittest
from copy import deepcopy
from unittest.mock import patch

from showcase.run_budget import RunBudgetLimits
from showcase.star_product_config import CORE_FEATURES
from tests.star_product_support import StarJobFixture
from tests.test_star_population_runtime import CAPACITY, PROBLEM, ROOT_ID, SPEC


class FaithfulPopulationJobTest(StarJobFixture, unittest.TestCase):
    def run_plain_submission(self, *, runtime=7200, timeout=15, capacity=CAPACITY,
                             selection_mode="population"):
        entered = threading.Barrier(2)
        concurrent = []

        def provider(request):
            role = request["role"]
            if role == "problem_intake":
                return deepcopy(SPEC)
            if role == "planner":
                plan = {"version": 1, "steps": [{
                    "step_id": "direct", "title": "Direct", "objective": PROBLEM,
                    "method_id": "direct", "obligation_ids": [ROOT_ID],
                    "auxiliary_goal_ids": [],
                }]}
                alternative = deepcopy(plan)
                alternative["steps"][0].update(step_id="construction", method_id="construction")
                return {**plan, "alternative_plans": [alternative],
                        "execution_selection": {"mode": selection_mode,
                                                "reason": "Two independent methods cover the goal."}}
            if role == "reasoner":
                try:
                    entered.wait(timeout=2)
                    concurrent.append(request)
                except threading.BrokenBarrierError:
                    pass
                return {"argument": "1+1=2", "claims": [
                    {"statement": "1+1=2", "label": "verified"}], "blocked": False}
            if role == "step_verifier":
                return {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
                        "objection": "", "obligation_evidence": [{
                            "obligation_id": ROOT_ID, "evidence_category": "format_check",
                            "claim_indexes": [0]}]}
            if role == "final_generator":
                return {"final_response": "1+1=2"}
            if role == "whole_solution_verifier":
                return {"verdict": "ACCEPT", "reason": "Complete answer."}
            return {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []}

        limits = RunBudgetLimits(max_model_calls=40, max_http_attempts=40,
                                 max_tokens=2_000_000, max_runtime_seconds=runtime)
        self.open_star([provider] * 40, SHOWCASE_FAITHFUL_AUTONOMOUS=True,
            SHOWCASE_STAR_FULL_ENABLED=True,
            SHOWCASE_STAR_FULL_FEATURES=dict.fromkeys(CORE_FEATURES | {
                "auto_problem_spec", "problem_spec", "proof_graph",
                "progress_scheduling", "serial_routes"}, True),
            SHOWCASE_STAR_FULL_BUDGET=limits,
            SHOWCASE_STAR_POPULATION_ENABLED=True,
            SHOWCASE_STAR_POPULATION_CAPACITY=capacity,
            SHOWCASE_STAR_POPULATION_REQUEST_TIMEOUT_SECONDS=timeout,
            # This separate advanced-preset budget must never replace the root.
            SHOWCASE_STAR_POPULATION_BUDGET=RunBudgetLimits(max_model_calls=99))
        pipeline = self.app.extensions["showcase_workspace_service"].star_pipeline
        with patch.object(pipeline, "full_gaps", return_value=[]):
            response = self.client.post("/api/agent/jobs", headers=self.headers(),
                json={"message": PROBLEM, "session_id": self.session})
            self.assertEqual(202, response.status_code, response.get_json())
            job_id = response.get_json()["job_id"]
            final = self.terminal(job_id, timeout=20)
        self.assertEqual("succeeded", final["status"], final)
        return job_id, final, concurrent

    def test_plain_submission_selects_parallel_routes_and_reloads_bound_delivery(self):
        job_id, final, concurrent = self.run_plain_submission()
        planner = next(item for item in self.outbound if item["role"] == "planner")
        self.assertIn("execution_selection only on the primary top-level plan", planner["instruction"])
        self.assertIn("alongside checkpoint in checkpoint replies", planner["instruction"])
        self.assertIn("NEVER include execution_selection in alternative_plans", planner["instruction"])
        self.assertIn("normal complete plans without execution_selection", planner["instruction"])
        self.assertIn("optional whole-proof directions as alternative complete plans", planner["instruction"])
        self.assertIn("not mandatory proof steps after a shared answer", planner["instruction"])
        self.assertIn("Each route must establish its own conclusions, equality conditions and completeness",
                      planner["instruction"])
        self.assertIn("Explore candidates are unverified", planner["instruction"])
        self.assertIn("never freeze their maximum or equality claims as established", planner["instruction"])
        self.assertIn("Choose one complete serial method when independent exploration adds no value",
                      planner["instruction"])
        self.assertIn("or its budget cost is not justified", planner["instruction"])
        solver = final["result"]["solver"]
        self.assertEqual("population", solver.get("execution_selection", {}).get("selected"))
        self.assertEqual(2, len(concurrent))
        self.assertEqual(2, len({item["call_id"] for item in concurrent}))
        self.assertEqual({job_id}, {item["run_id"] for item in self.outbound})
        self.assertEqual(40, final["result"]["budget"]["limits"]["max_model_calls"])
        self.assertEqual(final["result"]["budget"]["deadline_at"],
                         solver["execution_selection"]["budget"]["deadline_at"])
        route_attempts = [item for item in final["result"]["request_attempts"]
                          if item["role"] in {"reasoner", "step_verifier"}]
        self.assertTrue(route_attempts)
        self.assertTrue(all(0 < item["effective_timeout_seconds"] <= 15 for item in route_attempts))
        final_attempts = [item for item in final["result"]["request_attempts"]
                          if item["role"] in {"final_generator", "whole_solution_verifier"}]
        self.assertEqual(2, len(final_attempts))
        self.assertTrue(all(15 < item["effective_timeout_seconds"] <= 30 for item in final_attempts))
        self.assertEqual(len(self.outbound), final["result"]["budget"]["logical_calls"])
        self.assertEqual(2, len(solver["population"]["routes"]))
        before = len(self.outbound)
        report = self.report(job_id)
        self.assertEqual("same_artifact", report["semantics"]["binding"])
        self.assertEqual("delivered", report["solver"]["solver"]["population"]["delivery"]["status"])
        self.assertEqual(final["result"]["final_response"], self.job(job_id)["result"]["final_response"])
        self.assertEqual(before, len(self.outbound))

    def test_population_proposal_with_insufficient_root_time_uses_serial_without_reset(self):
        job_id, final, concurrent = self.run_plain_submission(runtime=180, timeout=30)
        selection = final["result"]["solver"]["execution_selection"]
        self.assertEqual("population", selection["requested"])
        self.assertEqual("serial", selection["selected"])
        self.assertEqual("root_budget_insufficient", selection["reason"])
        self.assertEqual([], concurrent)
        self.assertNotIn("population", final["result"]["solver"])
        self.assertEqual(180, final["result"]["budget"]["limits"]["max_runtime_seconds"])
        self.assertEqual(selection, self.job(job_id)["result"]["solver"]["execution_selection"])

    def test_unavailable_population_preserves_admission_reason_for_either_model_choice(self):
        for capacity, timeout, mode, reason in (
            ({**CAPACITY, "status": "unverified"}, 15, "population", "population_capacity_unverified"),
            (CAPACITY, 31, "population", "population_request_timeout_invalid"),
            ({**CAPACITY, "worker_slots": 0}, 15, "serial", "population_capacity_invalid"),
        ):
            with self.subTest(reason=reason, mode=mode):
                job_id, final, concurrent = self.run_plain_submission(
                    capacity=capacity, timeout=timeout, selection_mode=mode)
                selection = final["result"]["solver"]["execution_selection"]
                self.assertEqual(reason, selection["reason"])
                self.assertEqual("serial", selection["selected"])
                self.assertEqual([], concurrent)
                planner = next(item for item in self.outbound if item["role"] == "planner")
                self.assertEqual(reason, planner["autonomous_routes"]["unavailable_reason"])
                before = len(self.outbound)
                self.assertEqual(selection, self.job(job_id)["result"]["solver"]["execution_selection"])
                self.assertEqual(before, len(self.outbound))
