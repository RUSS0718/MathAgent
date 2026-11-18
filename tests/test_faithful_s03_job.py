"""S03 ProblemSpec through the authenticated public STAR Job boundary."""

import os
import unittest
import uuid
from unittest.mock import patch

import requests

from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import StarJobFixture

PROBLEM = "1+1"
PRIVATE_STATEMENT = "PRIVATE_ROOT_STATEMENT_4c16a9"
SPEC = {
    "specification_version": 1,
    "original_problem": PROBLEM,
    "domain": "integers",
    "quantifiers": ["the displayed expression is evaluated"],
    "assumptions": ["the standard integer operations apply"],
    "directions": ["evaluate"],
    "output_requirements": ["give the exact value"],
    "root_obligations": [{
        "obligation_id": "root:value",
        "obligation_type": "universal",
        "statement": PRIVATE_STATEMENT,
    }],
    "auxiliary_goals": [],
}
FEATURES = {
    "problem_spec": True,
    "final_generation": True,
    "final_solution_review": True,
    "context_pack": True,
}
ENDPOINT = "http://127.0.0.1:5000/api/v1/chat/completions"
CAPACITY_POLICY = {
    "version": "context-capacity-v1", "profile_version": "s03-controlled-v1",
    "provider": "intern", "model": "intern-s2", "endpoint": ENDPOINT,
    "cap_source": "controlled_test_only", "cap_source_date": "2026-11-07",
    "input_cap_tokens": None, "output_reserve_tokens": 256,
    "safety_margin_tokens": 10,
    "token_estimator_version": "utf8-bytes-per-three-v1",
}
REPLIES = [
    {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []},
    {"version": 1, "steps": [{
        "step_id": "prove-value", "title": "evaluate", "objective": "prove the value",
        "obligation_ids": ["root:value"], "auxiliary_goal_ids": [],
    }]},
    {"argument": "1+1=2", "claims": [{"statement": "1+1=2", "label": "hard-verify"}],
     "blocked": False},
    {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": "",
     "obligation_evidence": [{"obligation_id": "root:value",
                               "evidence_category": "universal_proof", "claim_indexes": [0]}]},
    {"final_response": "2"},
    {"verdict": "ACCEPT", "reason": "The answer covers the original request."},
]


class FaithfulS03PublicJobTest(StarJobFixture, unittest.TestCase):
    def open_spec_job(self):
        self.enterContext(patch.dict(os.environ, {"INTERN_API_BASE": ENDPOINT}))
        self.open_star(
            REPLIES,
            SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_CONTEXT_CAPACITY=CAPACITY_POLICY,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                max_model_calls=8, max_http_attempts=8, max_tool_calls=0,
                max_tokens=100_000, max_runtime_seconds=1_100,
            ),
        )

    def test_enabled_spec_runs_through_job_report_and_replay_without_leaking_spec_text(self):
        self.open_spec_job()
        headers = self.headers()
        request = {
            "message": PROBLEM,
            "session_id": self.session,
            "solver_mode": "star_limited",
            "problem_spec": SPEC,
        }
        created = self.client.post("/api/agent/jobs", json=request, headers=headers)
        self.assertEqual(202, created.status_code, created.get_json())
        job_id = created.get_json()["job_id"]
        terminal = self.terminal(job_id)
        self.assertEqual("succeeded", terminal["status"], terminal)

        report_response = self.client.get(f"/api/agent/jobs/{job_id}/report").get_json()
        report = report_response["report"]
        progress = report_response["solver"]["solver"]["progress"]
        self.assertEqual({"covered": 1, "total": 1,
                          "items": [{"ordinal": 1, "type": "universal", "status": "satisfied"}]},
                         progress["root_obligations"])
        self.assertEqual("accepted", report["semantics"]["whole_review"])
        self.assertEqual("same_artifact", report["semantics"]["binding"])
        context = report["semantics"]["context_capacity"]
        self.assertEqual(6, context["pack_count"])
        self.assertEqual(1, context["packs"][-1]["specification_version"])
        self.assertTrue(all(item.get("problem_spec_version") == 1 for item in self.outbound))
        verifier_index = next(
            index for index, item in enumerate(self.outbound)
            if item.get("role") == "step_verifier"
        )
        verifier_instructions = "\n".join(
            message["content"] for message in self.outbound_messages[verifier_index]
            if message.get("role") == "system"
        )
        self.assertIn("current WorkUnit", verifier_instructions)
        self.assertIn("category label, not proof", verifier_instructions)
        self.assertIn("completeness_proof", verifier_instructions)
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        self.assertEqual(6, evidence["budget"]["logical_calls"])
        self.assertEqual(6, evidence["budget"]["http_attempts"])
        self.assertEqual(0, evidence["budget"]["reserved_tokens"])
        self.assertEqual(6, self.post.call_count)
        self.assertEqual(SPEC, self.app.extensions["showcase_workspace_service"].store.problem_spec(job_id))

        events = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        public_text = repr(report_response) + events
        self.assertNotIn(PRIVATE_STATEMENT, public_text)
        replay = self.client.post("/api/agent/jobs", json=request, headers=headers)
        self.assertEqual(200, replay.status_code, replay.get_json())
        self.assertEqual(job_id, replay.get_json()["job_id"])
        self.assertEqual(6, self.post.call_count)

    def test_oversized_spec_is_rejected_without_truncating_the_stored_problem(self):
        self.enterContext(patch.dict(os.environ, {"INTERN_API_BASE": ENDPOINT}))
        capacity = {**CAPACITY_POLICY, "input_cap_tokens": 20_000}
        self.open_star(
            [*REPLIES, *REPLIES],
            SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_CONTEXT_CAPACITY=capacity,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                max_model_calls=8, max_http_attempts=8, max_tool_calls=0,
                max_tokens=100_000, max_runtime_seconds=1_100,
            ),
        )
        headers = self.headers()
        small_request = {
            "message": PROBLEM,
            "session_id": self.session,
            "solver_mode": "star_limited",
            "problem_spec": SPEC,
        }
        small_created = self.client.post(
            "/api/agent/jobs", json=small_request, headers=headers
        )
        self.assertEqual(202, small_created.status_code, small_created.get_json())
        small_id = small_created.get_json()["job_id"]
        self.assertEqual("succeeded", self.terminal(small_id)["status"])
        dispatched_before_large_spec = self.post.call_count

        long_statement = "complete-boundary:" + ("candidate " * 20_000)
        large_spec = {
            **SPEC,
            "assumptions": [long_statement],
            "root_obligations": [{**SPEC["root_obligations"][0], "statement": long_statement}],
        }
        large_request = {**small_request, "problem_spec": large_spec}
        large_created = self.client.post(
            "/api/agent/jobs", json=large_request, headers=self.headers()
        )
        self.assertEqual(202, large_created.status_code, large_created.get_json())
        large_id = large_created.get_json()["job_id"]
        large_terminal = self.terminal(large_id)
        self.assertEqual("failed", large_terminal["status"], large_terminal)
        self.assertEqual("context_capacity_exceeded", large_terminal["error"], large_terminal)

        service = self.app.extensions["showcase_workspace_service"]
        self.assertEqual(large_spec, service.store.problem_spec(large_id))
        self.assertEqual(dispatched_before_large_spec, self.post.call_count)

    def test_problem_spec_is_required_only_when_the_server_feature_is_enabled(self):
        self.open_spec_job()
        response = self.client.post(
            "/api/agent/jobs",
            json={"message": PROBLEM, "session_id": self.session, "solver_mode": "star_limited"},
            headers=self.headers(),
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual("problem_spec_required", response.get_json()["error"])
        self.assertEqual(0, self.post.call_count)

    def test_unknown_call_keeps_spec_deadline_and_budget_until_explicit_retry(self):
        self.enterContext(patch.dict(os.environ, {"INTERN_API_BASE": ENDPOINT}))
        replies = [
            requests.Timeout("scripted unknown outcome"),
            {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []},
            {"version": 1, "steps": [{
                "step_id": "prove-value", "title": "evaluate", "objective": "prove the value",
                "obligation_ids": ["root:value"], "auxiliary_goal_ids": [],
            }]},
            {"argument": "1+1=2", "claims": [{"statement": "1+1=2", "label": "hard-verify"}],
             "blocked": False},
            {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": "",
             "obligation_evidence": [{"obligation_id": "root:value",
                                       "evidence_category": "universal_proof",
                                       "claim_indexes": [0]}]},
            {"final_response": "2"},
            {"verdict": "ACCEPT", "reason": "The answer covers the original request."},
        ]
        self.open_star(
            replies,
            SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_CONTEXT_CAPACITY=CAPACITY_POLICY,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                max_model_calls=12, max_http_attempts=12, max_tool_calls=0,
                max_tokens=100_000, max_runtime_seconds=1_100,
            ),
        )
        request = {
            "message": PROBLEM,
            "session_id": self.session,
            "solver_mode": "star_limited",
            "problem_spec": SPEC,
        }
        created = self.client.post(
            "/api/agent/jobs", json=request, headers=self.headers()
        )
        self.assertEqual(202, created.status_code, created.get_json())
        job_id = created.get_json()["job_id"]
        interrupted = self.terminal(job_id)
        self.assertEqual("failed", interrupted["status"])
        old_budget = interrupted["result"]["budget"]
        self.assertEqual(1, old_budget["unknown_attempts"])
        self.assertEqual(SPEC, self.app.extensions[
            "showcase_workspace_service"
        ].store.problem_spec(job_id))
        unknown = interrupted["result"]["solver"]["recovery"]["unknown_calls"]
        self.assertEqual(1, len(unknown))

        rejected = self.client.post(
            f"/api/agent/jobs/{job_id}/resume", json={}, headers=self.headers()
        )
        self.assertEqual(409, rejected.status_code)
        self.assertEqual(1, self.post.call_count)

        resumed = self.client.post(
            f"/api/agent/jobs/{job_id}/resume",
            json={"retry_call": {
                "call_id": unknown[0]["call_id"], "new_call_id": str(uuid.uuid4()),
            }},
            headers=self.headers(),
        )
        self.assertEqual(202, resumed.status_code, resumed.get_json())
        completed = self.terminal(job_id)
        self.assertEqual("succeeded", completed["status"], completed)
        budget = completed["result"]["budget"]
        self.assertEqual(old_budget["deadline_at"], budget["deadline_at"])
        self.assertEqual(1, budget["unknown_attempts"])
        self.assertEqual(7, self.post.call_count)
        self.assertTrue(all(item.get("problem_spec_version") == 1 for item in self.outbound))

    def test_default_closed_job_rejects_problem_spec_without_dispatch(self):
        self.open_star(REPLIES)
        response = self.client.post(
            "/api/agent/jobs",
            json={"message": PROBLEM, "session_id": self.session,
                  "solver_mode": "star_limited", "problem_spec": SPEC},
            headers=self.headers(),
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual("problem_spec_feature_disabled", response.get_json()["error"])
        self.assertEqual(0, self.post.call_count)

    def test_server_presets_keep_problem_spec_off_by_default_and_require_review_prerequisites(self):
        from showcase.star_product_config import full_config, limited_config

        limits = RunBudgetLimits(max_model_calls=8, max_http_attempts=8, max_tool_calls=0)
        self.assertIsNot(full_config(limits)["features"].get("problem_spec"), True)
        self.assertIsNot(limited_config(limits)["features"].get("problem_spec"), True)
        with self.assertRaisesRegex(ValueError, "problem_spec_requires_final_generation_and_review"):
            limited_config(limits, {"problem_spec": True})


if __name__ == "__main__":
    unittest.main()
