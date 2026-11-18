"""Dependency routing through the real public Job and provider HTTP seams."""

import os
import unittest
import uuid
from copy import deepcopy
from unittest.mock import patch

from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import ACCEPT, SOLVED, StarJobFixture
from tests.test_faithful_s03_job import CAPACITY_POLICY, ENDPOINT, SPEC


class DependencyRoutingJobTest(StarJobFixture, unittest.TestCase):
    def test_independent_enumeration_and_completeness_still_use_one_explore_and_review(self):
        spec = deepcopy(SPEC)
        spec["root_obligations"] = [
            {"obligation_id": "roots", "obligation_type": "enumeration", "statement": "List roots"},
            {"obligation_id": "complete", "obligation_type": "completeness", "statement": "Exclude others"}]
        self.enterContext(patch.dict(os.environ, {"INTERN_API_BASE": ENDPOINT}))
        self.open_star([spec, {**SOLVED, "solution_candidate": "1+1=2 by integer addition."}, ACCEPT],
            SHOWCASE_STAR_ROUTING_POLICY_VERSION="objective-dependency-routing-v1",
            SHOWCASE_STAR_FEATURES=dict.fromkeys({"adaptive_solving", "auto_problem_spec",
                "problem_spec", "final_generation", "final_solution_review", "context_pack"}, True),
            SHOWCASE_STAR_CONTEXT_CAPACITY=CAPACITY_POLICY,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8))
        job_id = self.create_job()
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"], final.get("error"))
        self.assertEqual(["problem_intake", "explore", "whole_solution_verifier"],
                         [r["role"] for r in self.outbound])
        self.assertEqual(3, final["result"]["budget"]["logical_calls"])
        self.report(job_id)
        self.client.get(f"/api/agent/jobs/{job_id}/answer")
        self.assertEqual(3, len(self.outbound))

    def test_incomplete_exploration_reaches_planner_and_reasoner_only_as_unverified_material(self):
        from tests.test_faithful_s03_job import REPLIES

        replies = deepcopy(REPLIES)
        replies[1]["steps"][0]["method_id"] = "direct"
        replies[0]["worked"] = ["UNVERIFIED_FINDING_190: evaluate by integer addition"]
        self.enterContext(patch.dict(os.environ, {"INTERN_API_BASE": ENDPOINT}))
        self.open_star([SPEC, *replies],
            SHOWCASE_STAR_ROUTING_POLICY_VERSION="objective-dependency-routing-v1",
            SHOWCASE_STAR_FEATURES=dict.fromkeys({"adaptive_solving", "auto_problem_spec",
                "problem_spec", "final_generation", "final_solution_review", "context_pack",
                "progress_scheduling"}, True),
            SHOWCASE_STAR_CONTEXT_CAPACITY=CAPACITY_POLICY,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=12, max_http_attempts=12))
        final = self.terminal(self.create_job())
        self.assertEqual("succeeded", final["status"], final.get("error"))
        explore = next(r for r in self.outbound if r["role"] == "explore")
        for role in ("planner", "reasoner"):
            request = next(r for r in self.outbound if r["role"] == role)
            finding = request["exploration_findings"][0]
            self.assertEqual("unverified_exploration", finding["provenance"])
            self.assertEqual(explore["call_id"], finding["source"]["call_id"])
            self.assertEqual(1, finding["source"]["specification_version"])
            self.assertIn("UNVERIFIED_FINDING_190", finding["worked"][0])
            self.assertNotIn("UNVERIFIED_FINDING_190", repr(request.get("valid_sources", [])))

    def test_legacy_and_new_runs_resume_with_their_frozen_policy_and_budget(self):
        import requests

        for adaptive, new_policy in ((False, False), (True, False), (True, True)):
            with self.subTest(adaptive=adaptive, new_policy=new_policy):
                features = dict.fromkeys({"auto_problem_spec", "problem_spec", "final_generation",
                    "final_solution_review", "context_pack"}, True)
                if adaptive:
                    features["adaptive_solving"] = True
                config = {"SHOWCASE_STAR_FEATURES": features,
                          "SHOWCASE_STAR_CONTEXT_CAPACITY": CAPACITY_POLICY,
                          "SHOWCASE_STAR_BUDGET": RunBudgetLimits(max_model_calls=12, max_http_attempts=12)}
                if new_policy:
                    config["SHOWCASE_STAR_ROUTING_POLICY_VERSION"] = "objective-dependency-routing-v1"
                candidate = "1+1=2 by integer addition."
                replies = [SPEC, requests.ReadTimeout("unknown"),
                           {**SOLVED, "solution_candidate": candidate}]
                if not adaptive:
                    replies.append({"solution_candidate": candidate})
                replies.append(ACCEPT)
                self.enterContext(patch.dict(os.environ, {"INTERN_API_BASE": ENDPOINT}))
                self.open_star(replies, **config)
                job_id = self.create_job()
                first = self.terminal(job_id)
                self.assertEqual("failed", first["status"])
                before = first["result"]["budget"]
                first_hashes = {p["config_hash"] for p in first["result"]["solver"]
                                ["semantics"]["context_capacity"]["packs"]}
                pipeline = self.app.extensions["showcase_workspace_service"].star_pipeline
                # Trusted server setting changes; the already-created Run must not migrate.
                pipeline.routing_policy_version = None if new_policy else "objective-dependency-routing-v1"
                rejected = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={}, headers=self.headers())
                self.assertEqual(409, rejected.status_code)
                old_id = first["result"]["solver"]["recovery"]["unknown_calls"][0]["call_id"]
                resumed = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={"retry_call": {
                    "call_id": old_id, "new_call_id": str(uuid.uuid4())}}, headers=self.headers())
                self.assertEqual(202, resumed.status_code, resumed.get_json())
                final = self.terminal(job_id)
                self.assertEqual("succeeded", final["status"], {
                    "error": final.get("error"), "faithful": final.get("result", {}).get("faithful"),
                    "roles": [r["role"] for r in self.outbound],
                    "recovery": final.get("result", {}).get("solver", {}).get("recovery")})
                after = final["result"]["budget"]
                self.assertEqual(before["deadline_at"], after["deadline_at"])
                self.assertEqual(before["limits"], after["limits"])
                self.assertEqual(before["reserved_tokens"], after["reserved_tokens"])
                self.assertEqual(1, after["unknown_attempts"])
                self.assertEqual(first_hashes, {p["config_hash"] for p in final["result"]["solver"]
                                 ["semantics"]["context_capacity"]["packs"]})
                self.assertEqual(4 if adaptive else 5, len(self.outbound))

    def test_dependencies_plan_before_solving_and_execute_ordered_work_units(self):
        spec = deepcopy(SPEC)
        spec["root_obligations"].append({
            "obligation_id": "root:conclusion", "obligation_type": "universal",
            "statement": "Use the evaluated value", "prerequisite_ids": ["root:value"],
        })
        plan = {"version": 1, "steps": [
            {"step_id": "value", "title": "evaluate", "objective": "evaluate 1+1",
             "obligation_ids": ["root:value"], "auxiliary_goal_ids": [], "method_id": "direct"},
            {"step_id": "conclusion", "title": "conclude", "objective": "use the value",
             "obligation_ids": ["root:conclusion"], "auxiliary_goal_ids": [],
             "depends_on": ["value"], "method_id": "direct"},
        ]}

        def reply(request):
            role = request["role"]
            if role == "planner":
                return plan
            if role == "reasoner":
                return {"argument": "1+1=2", "claims": [{"statement": "1+1=2",
                        "label": "hard-verify"}], "blocked": False}
            if role == "step_verifier":
                obligation = "root:value" if request["step"]["step_id"] == "value" else "root:conclusion"
                return {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
                        "objection": "", "obligation_evidence": [{"obligation_id": obligation,
                        "evidence_category": "universal_proof", "claim_indexes": [0]}]}
            if role == "final_generator":
                return {"final_response": "2"}
            if role == "explore":
                return {**SOLVED, "solution_candidate": "1+1=2"}
            return ACCEPT

        self.enterContext(patch.dict(os.environ, {"INTERN_API_BASE": ENDPOINT}))
        self.open_star([spec, *([reply] * 10)],
            SHOWCASE_STAR_ROUTING_POLICY_VERSION="objective-dependency-routing-v1",
            SHOWCASE_STAR_FEATURES=dict.fromkeys({"adaptive_solving", "auto_problem_spec",
                "problem_spec", "final_generation", "final_solution_review", "context_pack",
                "progress_scheduling"}, True),
            SHOWCASE_STAR_CONTEXT_CAPACITY=CAPACITY_POLICY,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=12, max_http_attempts=12))
        job_id = self.create_job()
        final = self.terminal(job_id)
        roles = [request["role"] for request in self.outbound]
        self.assertEqual("planner", roles[1], roles)
        self.assertEqual("succeeded", final["status"], final)
        self.assertEqual(["problem_intake", "planner", "reasoner", "step_verifier",
                          "reasoner", "step_verifier", "final_generator",
                          "whole_solution_verifier"], roles)
        self.assertEqual(["value", "conclusion"], [request["step"]["step_id"]
                         for request in self.outbound if request["role"] == "reasoner"])
        self.assertEqual("2", final["result"]["final_response"])
        events = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        self.assertIn("objective_dependencies", events)
        budget = final["result"]["budget"]
        self.report(job_id)
        self.assertEqual(budget, self.job(job_id)["result"]["budget"])
        self.assertEqual(8, len(self.outbound))
