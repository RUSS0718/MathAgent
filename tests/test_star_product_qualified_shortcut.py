"""Scalar Explore answers cannot discharge typed proof obligations."""

import json
import unittest
from copy import deepcopy

from showcase.run_budget import RunBudgetLimits
from showcase.solver_harness.final_binding import delivery_verification, review_binding
from showcase.solver_harness.storage import SolverStateStore
from tests.star_product_support import ACCEPT, SOLVED, StarJobFixture
from tests.test_star_population_runtime import PROBLEM, SPEC


class QualifiedShortcutJobTest(StarJobFixture, unittest.TestCase):
    def test_scalar_presentations_cannot_bypass_proof_qualification(self):
        problem = "Count the positive divisors of 6 and prove the list is complete."
        spec = {**SPEC, "original_problem": problem, "root_obligations": [{
            "obligation_id": "proof", "obligation_type": "completeness",
            "statement": "Prove every positive divisor is listed.",
        }]}
        cases = [(text, True) for text in (
            "$4$", r"\boxed{4}", "4。", "4/2.0", "4.", "$$4$$",
            r"\(4\)", r"\[4\]", r"$\boxed{4}$。", " -4.5e+1 / +2.0 ",
        )] + [(text, False) for text in (
            "6=2×3, so its divisors are exactly 1, 2, 3, 6. There are 4.",
            r"\boxed{4} divisors, since 6=2×3 and each prime exponent is 0 or 1.",
        )]
        self.open_star([reply for text, _ in cases for reply in (
            spec, {**SOLVED, "solution_candidate": text}, {"solution_candidate": text}, ACCEPT,
        )], SHOWCASE_STAR_FEATURES={"auto_problem_spec": True, "problem_spec": True,
                                   "final_generation": True, "final_solution_review": True},
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=4, max_http_attempts=4))
        for index, (text, scalar) in enumerate(cases, 1):
            with self.subTest(candidate=text):
                response = self.client.post("/api/agent/jobs", headers=self.headers(), json={
                    "message": problem, "session_id": self.session,
                    "solver_mode": "star_limited_best_effort"})
                self.assertEqual(202, response.status_code, response.get_json())
                job_id = response.get_json()["job_id"]
                job = self.terminal(job_id)
                report = self.report(job_id)
                self.assertEqual("rejected" if scalar else "accepted",
                                 report["semantics"]["whole_review"])
                self.assertEqual("failed" if scalar else "succeeded", job["status"])
                if scalar:
                    self.assertEqual("no_eligible_candidate", job["result"]["solver"]["best_effort"]["status"])
                    self.assertNotEqual(text, job["result"]["final_response"])
                    whole_check = next(check for check in report["checks"]["history"]
                                       if check["scope"] == "whole_solution_llm_review")
                    self.assertEqual("REJECT", whole_check["runtime_qualification"]["verdict"])
                else:
                    self.assertEqual(text, job["result"]["final_response"])
                self.assertEqual(4, report["budget"]["logical_calls"])
                self.assertEqual(4, report["budget"]["http_attempts"])
                self.assertEqual(index * 4, len(self.outbound))

    def test_scalar_veto_remains_auditable_and_ineligible_at_exact_budget(self):
        problem = "Count the positive divisors of 6 and prove the list is complete."
        spec = {**SPEC, "original_problem": problem, "root_obligations": [{
            "obligation_id": "proof", "obligation_type": "completeness",
            "statement": "Prove every positive divisor is listed.",
        }]}
        reason = "scalar_candidate_cannot_discharge_proof_obligations"
        self.open_star([spec, {**SOLVED, "solution_candidate": "4"},
                        {"solution_candidate": "4"}, ACCEPT],
            SHOWCASE_STAR_FEATURES={"auto_problem_spec": True, "problem_spec": True,
                                   "final_generation": True, "final_solution_review": True},
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=4, max_http_attempts=4))
        response = self.client.post("/api/agent/jobs", headers=self.headers(), json={
            "message": problem, "session_id": self.session,
            "solver_mode": "star_limited_best_effort"})
        self.assertEqual(202, response.status_code, response.get_json())
        job_id = response.get_json()["job_id"]
        job = self.terminal(job_id)
        report = self.report(job_id)
        store = SolverStateStore(self.app.extensions["loopback_store"]._connection)
        persisted = store.get_run(job_id)
        record = persisted["state"]["whole_solution_reviews"][-1]
        call = persisted["state"]["calls"][record["source"]["call_id"]]
        self.assertEqual("completed", call["status"])
        self.assertEqual("ACCEPT", call["response"]["verdict"])
        self.assertEqual("ACCEPT", record["verdict"])
        qualification = record["runtime_qualification"]
        self.assertEqual("REJECT", qualification["verdict"])
        self.assertEqual(reason, qualification["reason"])
        veto = next(event for event in persisted["events"]
                    if event["event_id"] == qualification["event_id"])
        self.assertEqual("solution_review_qualification", veto["type"])
        self.assertEqual(record["source"], veto["source"])
        self.assertEqual(record["artifact"], veto["artifact"])
        self.assertEqual("REJECT", veto["verdict"])
        self.assertEqual({"whole_review": "rejected", "binding": "same_artifact"},
                         review_binding(persisted, "4"))
        self.assertFalse(delivery_verification(persisted, "4")[0])
        without_veto = {**persisted, "events": [event for event in persisted["events"]
                                               if event["event_id"] != veto["event_id"]]}
        self.assertEqual("invalid_source", review_binding(without_veto, "4")["whole_review"])
        self.assertFalse(delivery_verification(without_veto, "4")[0])
        mismatched = deepcopy(persisted)
        mismatched["state"]["whole_solution_reviews"][-1]["verdict"] = "REJECT"
        self.assertEqual("invalid_source", review_binding(mismatched, "4")["whole_review"])
        self.assertEqual("rejected", report["semantics"]["whole_review"])
        self.assertEqual("failed", job["status"])
        self.assertNotEqual("4", job["result"]["final_response"])
        self.assertEqual("no_eligible_candidate", job["result"]["solver"]["best_effort"]["status"])
        latest = {item["candidate_id"]: item
                  for item in persisted["state"]["candidate_registry"]}
        self.assertTrue(latest)
        for candidate in latest.values():
            self.assertFalse(candidate["selection_eligible"])
            self.assertNotEqual("whole_reviewed", candidate["review_state"])
            self.assertIn(reason, candidate["known_objections"])
        self.assertEqual("needs_review", report["checks"]["acceptance"])
        whole_check = next(check for check in report["checks"]["history"]
                           if check["scope"] == "whole_solution_llm_review")
        self.assertEqual(qualification, whole_check["runtime_qualification"])
        self.assertIn("runtime_qualification_rejected", whole_check["findings"])
        self.assertEqual(report["semantics"], job["result"]["solver"]["semantics"])
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        self.assertEqual(report["semantics"], evidence["semantics"])
        replay = self.client.get(f"/api/agent/jobs/{job_id}/candidate-replay").get_json()
        self.assertTrue(replay["audit"]["matches_persisted_decision"])
        self.assertEqual(4, report["budget"]["logical_calls"])
        self.assertEqual(4, report["budget"]["http_attempts"])
        self.assertEqual(["problem_intake", "explore", "explore_polish", "whole_solution_verifier"],
                         [request["role"] for request in self.outbound])

    def test_scalar_with_completeness_obligation_retains_finding_then_plans(self):
        problem = "Count the positive divisors of 6 and prove the list is complete."
        solution = "6=2×3, so its positive divisors are exactly 1, 2, 3, 6. There are 4."
        spec = {
            "specification_version": 1, "original_problem": problem,
            "domain": "positive integers", "quantifiers": [], "assumptions": [],
            "directions": ["enumeration", "completeness"],
            "output_requirements": ["count", "completeness proof"],
            "root_obligations": [
                {"obligation_id": "count", "obligation_type": "enumeration",
                 "statement": "Count the positive divisors."},
                {"obligation_id": "proof", "obligation_type": "completeness",
                 "statement": "Prove every positive divisor is listed."},
            ], "auxiliary_goals": [],
        }
        plan = {"version": 1, "steps": [{
            "step_id": "divisors", "title": "Count and justify", "objective": problem,
            "obligation_ids": ["count", "proof"], "auxiliary_goal_ids": [],
        }]}
        step = {"argument": solution, "blocked": False,
                "claims": [{"statement": solution, "label": "easy-verify"}]}
        review = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
                  "objection": "", "obligation_evidence": [
                      {"obligation_id": root, "evidence_category": category, "claim_indexes": [0]}
                      for root, category in (("count", "enumeration_result"),
                                             ("proof", "completeness_proof"))]}
        self.open_star([
            spec, {**SOLVED, "solution_candidate": "4", "worked": ["counted divisors"]},
            {"solution_candidate": "4"}, ACCEPT, plan, step, review,
            {"final_response": solution}, ACCEPT,
        ], SHOWCASE_STAR_FEATURES={"auto_problem_spec": True, "problem_spec": True,
                                  "final_generation": True, "final_solution_review": True},
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=9, max_http_attempts=9))
        response = self.client.post("/api/agent/jobs", headers=self.headers(), json={
            "message": problem, "session_id": self.session, "solver_mode": "star_limited"})
        self.assertEqual(202, response.status_code, response.get_json())
        job_id = response.get_json()["job_id"]
        job = self.terminal(job_id)
        self.assertIn("planner", [request["role"] for request in self.outbound])
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual(solution, job["result"]["final_response"])
        planner = next(request for request in self.outbound if request["role"] == "planner")
        finding = planner["exploration_findings"][0]
        self.assertEqual("4", finding["solution_candidate"])
        self.assertEqual(["counted divisors"], finding["worked"])
        self.assertEqual(spec, planner["problem_spec"])
        self.assertEqual({job_id}, {request["run_id"] for request in self.outbound})
        budget = self.report(job_id)["budget"]
        self.assertEqual(9, budget["logical_calls"])
        self.assertEqual(9, budget["http_attempts"])
        self.assertEqual(9, budget["limits"]["max_model_calls"])
        stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        events = [json.loads(line[6:]) for line in stream.splitlines() if line.startswith("data: ")]
        rejected = next(event for event in events
                        if event.get("solver_event_type") == "solution_review_assessed")
        self.assertEqual("REJECT", rejected["verdict"])
        self.assertEqual("PLAN", rejected["next_phase"])

    def test_scalar_numerical_spec_keeps_complete_explore_shortcut(self):
        self.open_star([SPEC, SOLVED, {"solution_candidate": "2"}, ACCEPT],
            SHOWCASE_STAR_FEATURES={"auto_problem_spec": True, "problem_spec": True,
                                   "final_generation": True, "final_solution_review": True},
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=4, max_http_attempts=4))
        response = self.client.post("/api/agent/jobs", headers=self.headers(), json={
            "message": PROBLEM, "session_id": self.session, "solver_mode": "star_limited"})
        self.assertEqual(202, response.status_code, response.get_json())
        job_id = response.get_json()["job_id"]
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual("2", job["result"]["final_response"])
        self.assertEqual(["problem_intake", "explore", "explore_polish", "whole_solution_verifier"],
                         [request["role"] for request in self.outbound])
        self.assertEqual(4, self.report(job_id)["budget"]["logical_calls"])
