import unittest

from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import StarJobFixture
from tests.test_faithful_s03_job import FEATURES, REPLIES, SPEC


class FaithfulS08PublicJobTest(StarJobFixture, unittest.TestCase):
    def test_stalled_primary_runs_one_alternate_through_independent_final_review(self):
        import os
        from unittest.mock import patch

        from showcase.run_budget import RunBudgetLimits
        from tests.test_faithful_s03_job import CAPACITY_POLICY, ENDPOINT, FEATURES, SPEC

        self.enterContext(patch.dict(os.environ, {"INTERN_API_BASE": ENDPOINT}))
        old_steps = [
            ("direct", "direct"),
            ("contradiction", "contradiction"),
            ("induction", "induction"),
            ("fourth", "direct"),
        ]
        initial_plan = {"version": 1, "steps": [
            {"step_id": step_id, "title": method, "objective": f"attempt by {method}",
             "method_id": method, "obligation_ids": ["root:value"],
             "auxiliary_goal_ids": []}
            for step_id, method in old_steps
        ]}
        alternate_plan = {"version": 2, "steps": [{
            "step_id": "alternate", "title": "compute", "objective": "compute the value",
            "method_id": "computation", "obligation_ids": ["root:value"],
            "auxiliary_goal_ids": [],
        }]}
        replies = [
            {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []},
            initial_plan,
        ]
        for step_id in ("direct", "contradiction", "induction"):
            replies.extend([
                {"argument": f"draft for {step_id}",
                 "claims": [{"statement": f"candidate for {step_id}",
                             "label": "hard-verify"}], "blocked": False},
                {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
                 "objection": ""},
            ])
        replies.extend([
            {"decision": "APPROVE_REPLAN", "reason_summary": "three methods stagnated",
             "plan_summary": "use a computation route", "forbidden_directions": [],
             "reusable_results": [], "trace_back_to": None},
            alternate_plan,
            {"argument": "1+1=2", "claims": [{"statement": "1+1=2",
                                                "label": "hard-verify"}], "blocked": False},
            {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": "",
             "obligation_evidence": [{"obligation_id": "root:value",
                                      "evidence_category": "universal_proof",
                                      "claim_indexes": [0]}]},
            {"final_response": "2"},
            {"verdict": "ACCEPT", "reason": "The answer covers the original request."},
        ])
        self.open_star(
            replies,
            SHOWCASE_STAR_FEATURES={**FEATURES, "progress_scheduling": True,
                                    "serial_routes": True},
            SHOWCASE_STAR_CONTEXT_CAPACITY=CAPACITY_POLICY,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                max_model_calls=24, max_http_attempts=24, max_tool_calls=0,
                max_tokens=100_000, max_runtime_seconds=1_100,
            ),
        )
        created = self.client.post(
            "/api/agent/jobs",
            json={"message": SPEC["original_problem"], "session_id": self.session,
                  "solver_mode": "star_limited", "problem_spec": SPEC},
            headers=self.headers(),
        )
        self.assertEqual(202, created.status_code, created.get_json())
        job_id = created.get_json()["job_id"]
        terminal = self.terminal(job_id)
        self.assertEqual("succeeded", terminal["status"], terminal)
        report_response = self.client.get(f"/api/agent/jobs/{job_id}/report").get_json()
        report = report_response["report"]
        solver = report_response["solver"]["solver"]
        self.assertEqual(1, solver["progress"]["root_obligations"]["covered"])
        self.assertEqual(2, solver["progress"]["plan_version"])
        routes = solver["progress"]["routes"]
        self.assertEqual(["primary", "alternate"], [item["kind"] for item in routes["items"]])
        primary, alternate = routes["items"]
        self.assertEqual("stalled", primary["status"])
        self.assertEqual(primary["route_id"], alternate["parent_route_id"])
        self.assertEqual("completed", alternate["status"])
        self.assertEqual("final_answer_bound", alternate["stop_reason"])
        self.assertIsNone(routes["active_route_id"])
        self.assertTrue(routes["decisions"])
        self.assertTrue(all(item["replayable"] for item in routes["decisions"]))
        self.assertEqual("accepted", report["semantics"]["whole_review"])
        self.assertEqual("same_artifact", report["semantics"]["binding"])
        self.assertEqual(0, len(self.replies))

    def test_serial_route_is_persisted_and_projected_without_private_frontier(self):
        replies = __import__("copy").deepcopy(REPLIES)
        replies[1]["steps"][0]["method_id"] = "computation"
        self.open_star(
            replies,
            SHOWCASE_STAR_FEATURES={**FEATURES, "context_pack": False,
                                    "progress_scheduling": True, "serial_routes": True},
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8),
        )
        created = self.client.post(
            "/api/agent/jobs",
            json={"message": SPEC["original_problem"], "session_id": self.session,
                  "solver_mode": "star_limited", "problem_spec": SPEC},
            headers=self.headers(),
        )
        self.assertEqual(202, created.status_code, created.get_json())
        job_id = created.get_json()["job_id"]
        terminal = self.terminal(job_id)
        self.assertEqual("succeeded", terminal["status"], terminal)
        report = self.report(job_id)
        routes = report["solver"]["solver"]["progress"]["routes"]
        self.assertEqual("serial-aprs-v1", routes["policy_version"])
        self.assertEqual(1, len(routes["items"]))
        self.assertEqual("primary", routes["items"][0]["kind"])
        self.assertEqual("completed", routes["items"][0]["status"])
        self.assertEqual("final_answer_bound", routes["items"][0]["stop_reason"])
        self.assertIsNone(routes["active_route_id"])
        self.assertTrue(routes["decisions"][-1]["replayable"])
        encoded = repr(report)
        self.assertNotIn(SPEC["root_obligations"][0]["statement"], encoded)
        self.assertNotIn("prove-value", encoded)
