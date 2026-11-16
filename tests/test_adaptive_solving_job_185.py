"""One public Job regression for optional direct review and read-only refresh."""

import os
import unittest
from unittest.mock import patch

from showcase.run_budget import RunBudgetLimits
from showcase.star_product_config import CORE_FEATURES
from tests.star_product_support import ACCEPT, SOLVED, RawProviderContent, StarJobFixture
from tests.test_faithful_s03_job import CAPACITY_POLICY, ENDPOINT, SPEC


class AdaptiveJobTest(StarJobFixture, unittest.TestCase):
    def test_live_profile_time_reserve_allows_planning_and_bound_delivery(self):
        from copy import deepcopy

        from llm_client import InternChatClient
        from showcase.adapters import InternModelAdapter
        from tests.test_faithful_s03_job import REPLIES

        self.enterContext(patch.dict(os.environ, {"INTERN_API_BASE": ENDPOINT}))
        replies = deepcopy(REPLIES)
        replies[1]["steps"][0]["method_id"] = "direct"
        self.open_star([SPEC, *replies],
            SHOWCASE_FAITHFUL_AUTONOMOUS=True,
            SHOWCASE_STAR_FULL_ENABLED=True,
            SHOWCASE_STAR_FULL_FEATURES=dict.fromkeys(CORE_FEATURES | {
                "adaptive_solving", "auto_problem_spec", "problem_spec", "context_pack",
                "proof_graph", "progress_scheduling", "serial_routes"}, True),
            SHOWCASE_STAR_ADAPTER=InternModelAdapter(
                InternChatClient(timeout=360, retry=3), max_tokens=256),
            SHOWCASE_STREAM_TIMEOUT_POLICY_VERSION="faithful-stream-v1",
            SHOWCASE_STAR_CONTEXT_CAPACITY=CAPACITY_POLICY,
            SHOWCASE_STAR_FULL_BUDGET=RunBudgetLimits(
                max_model_calls=48, max_http_attempts=48, max_tool_calls=8,
                max_tokens=2097152, max_runtime_seconds=3600))
        pipeline = self.app.extensions["showcase_workspace_service"].star_pipeline
        self.enterContext(patch.object(pipeline, "full_gaps", return_value=[]))
        response = self.client.post("/api/agent/jobs", headers=self.headers(),
            json={"message": "1+1", "session_id": self.session})
        job_id = response.get_json()["job_id"]
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"], final.get("result", {}).get("faithful"))
        self.assertIn("planner", [r["role"] for r in self.outbound])
        self.assertEqual("2", final["result"]["final_response"])
        budget = final["result"]["budget"]
        self.assertEqual(3600, budget["deadline_at"] - budget["started_at"])
        self.assertEqual(7, budget["http_attempts"])
        self.job(job_id)
        self.assertEqual(7, len(self.outbound))

    def test_empty_candidate_repairs_once_and_spends_preserved_review_slot(self):
        self.open_adaptive([SPEC, RawProviderContent(""),
                           {**SOLVED, "solution_candidate": "1+1=2 by integer addition."}, ACCEPT])
        response = self.client.post("/api/agent/jobs", headers=self.headers(),
            json={"message": "1+1", "session_id": self.session})
        final = self.terminal(response.get_json()["job_id"])
        self.assertEqual("succeeded", final["status"], final.get("error"))
        self.assertEqual(["problem_intake", "explore", "explore", "whole_solution_verifier"],
                         [r["role"] for r in self.outbound])
        self.assertTrue(self.outbound[2]["call_id"].endswith(":repair-1"))

    def test_direct_dispatch_preserves_review_and_repair_slots(self):
        self.open_adaptive([SPEC, SOLVED, ACCEPT], calls=3)
        response = self.client.post("/api/agent/jobs", headers=self.headers(),
            json={"message": "1+1", "session_id": self.session})
        job_id = response.get_json()["job_id"]
        final = self.terminal(job_id)
        self.assertEqual("failed", final["status"])
        self.assertEqual(1, len(self.outbound))
        self.assertEqual("adaptive_closing_reserve_required",
                         final["result"]["solver"]["budget_exhaustion_reason"])
        self.job(job_id)
        self.assertEqual(1, len(self.outbound))

    def open_adaptive(self, replies, *, calls=4):
        """Wire the real public pipeline with finitely scripted HTTP responses."""
        self.enterContext(patch.dict(os.environ, {"INTERN_API_BASE": ENDPOINT}))
        self.open_star(replies,
            SHOWCASE_FAITHFUL_AUTONOMOUS=True,
            SHOWCASE_STAR_FULL_ENABLED=True,
            SHOWCASE_STAR_FULL_FEATURES=dict.fromkeys(CORE_FEATURES | {
                "adaptive_solving", "auto_problem_spec", "problem_spec", "context_pack",
                "proof_graph", "progress_scheduling", "serial_routes"}, True),
            SHOWCASE_STAR_CONTEXT_CAPACITY=CAPACITY_POLICY,
            SHOWCASE_STAR_FULL_BUDGET=RunBudgetLimits(max_model_calls=calls, max_http_attempts=calls))
        pipeline = self.app.extensions["showcase_workspace_service"].star_pipeline
        self.enterContext(patch.object(pipeline, "full_gaps", return_value=[]))

    def test_plain_job_delivers_bound_answer_and_refresh_dispatches_nothing(self):
        self.open_adaptive([SPEC, {**SOLVED, "solution_candidate": "1+1=2 by integer addition."}, ACCEPT])
        response = self.client.post("/api/agent/jobs", headers=self.headers(),
            json={"message": "1+1", "session_id": self.session})
        self.assertEqual(202, response.status_code)
        job_id = response.get_json()["job_id"]
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"], final)
        self.assertEqual(3, final["result"]["budget"]["logical_calls"])
        self.assertEqual("adaptive-solving-v1", final["result"]["solver"]["adaptive_solving"]["version"])
        self.assertEqual(["problem_intake", "explore", "whole_solution_verifier"],
                         [r["role"] for r in self.outbound])
        self.assertEqual(final["result"]["budget"], self.job(job_id)["result"]["budget"])
        self.report(job_id)
        self.assertEqual(3, len(self.outbound))

    def test_undefined_intake_dependency_gets_one_protocol_repair_before_solving(self):
        from copy import deepcopy

        invalid = deepcopy(SPEC)
        invalid["root_obligations"][0]["prerequisite_ids"] = ["missing_auxiliary"]
        self.open_adaptive([invalid, SPEC,
                           {**SOLVED, "solution_candidate": "1+1=2 by integer addition."}, ACCEPT], calls=5)
        response = self.client.post("/api/agent/jobs", headers=self.headers(),
            json={"message": "1+1", "session_id": self.session})
        final = self.terminal(response.get_json()["job_id"])
        self.assertEqual("succeeded", final["status"], final.get("error"))
        initial, repaired = self.outbound[:2]
        self.assertEqual("problem_intake", repaired["role"])
        self.assertEqual(initial["call_id"] + ":repair-1", repaired["call_id"])
        self.assertIn("unknown objective", str(repaired.get("format_repair")))
        self.assertEqual(4, len(self.outbound))

    def test_intake_semantic_repair_is_bounded_and_unknown_is_never_replayed(self):
        from copy import deepcopy

        import requests

        invalid = deepcopy(SPEC)
        invalid["root_obligations"][0]["prerequisite_ids"] = ["missing_auxiliary"]
        self.open_adaptive([invalid, requests.ReadTimeout("remote result unknown")], calls=4)
        response = self.client.post("/api/agent/jobs", headers=self.headers(),
            json={"message": "1+1", "session_id": self.session})
        job_id = response.get_json()["job_id"]
        final = self.terminal(job_id)
        self.assertEqual("failed", final["status"])
        self.assertEqual(1, len(final["result"]["solver"]["recovery"]["unknown_calls"]))
        self.job(job_id)
        self.assertEqual(2, len(self.outbound))
