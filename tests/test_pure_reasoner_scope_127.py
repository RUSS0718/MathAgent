"""Pure Reasoner mode leaves independent Verifier computation on its original ledger."""

import unittest
from copy import deepcopy

from showcase.run_budget import RunBudgetLimits, current_budget
from showcase.solver_harness import (
    ScriptedMetaPort,
    ScriptedModelPort,
    ScriptedToolPort,
    ScriptedVerifierPort,
    SolverHarness,
)
from showcase.tools import ToolRegistry
from tests import test_star_product_guidance as guidance
from tests import test_star_product_verifier_compute as compute
from tests.star_product_support import ACCEPT, StarJobFixture
from tests.test_star_product_tools import NEED_PLAN, PLAN, STEP


class PureReasonerScopeTest(StarJobFixture, unittest.TestCase):
    def test_model_cannot_claim_verifier_role_for_its_own_precheck(self):
        report = deepcopy(STEP)
        report["claims"][0]["tool_request"].update(role="step_verifier", source_role="step_verifier")
        tool = ScriptedToolPort([])
        with SolverHarness(
            config={"features": {"local_code_tool": True, "meta_guidance": True},
                    "allowed_tools": ["polynomial_check"], "max_model_calls": 8},
            model_port=ScriptedModelPort([{**guidance.PLAIN, "blocked": True}, report]),
            meta_port=ScriptedMetaPort([guidance.GUIDANCE]),
            verifier_port=ScriptedVerifierPort([compute.CONTINUE]), tool_port=tool,
        ) as harness:
            result = harness.solve("compute", {"plan": PLAN})
        self.assertEqual([], tool.requests)
        self.assertEqual("pure_reasoning_denied", result["state"]["tool_receipts"][0]["reason"])

    def test_read_tools_follow_the_same_role_scope(self):
        with SolverHarness(config={"features": {"skills": True}},
                           meta_port=ScriptedMetaPort([guidance.GUIDANCE])) as harness:
            harness.solve("compute", {"run_id": "pure-scope", "meta_guidance": {"failure_type": "stuck"}})
            self.assertFalse(harness.execute_tool_request(
                "pure-scope", role="reasoner", tool="read_state")["ok"])
            self.assertTrue(harness.execute_tool_request(
                "pure-scope", role="step_verifier", tool="read_ledger")["ok"])
            self.assertFalse(harness.execute_tool_request(
                "pure-scope", role="meta", tool="read_ledger")["ok"])

    def test_verifier_can_compute_while_reasoner_cannot_and_quota_still_applies(self):
        for quota in (1, 0):
            with self.subTest(tool_quota=quota):
                actual = []
                registry = ToolRegistry()
                registry.register("polynomial_check", lambda args: actual.append(
                    current_budget().snapshot()["tool_calls"]) or 2)
                replies = [NEED_PLAN, PLAN, {**guidance.PLAIN, "blocked": True},
                           guidance.GUIDANCE, STEP, compute.PREMATURE, compute.CONTINUE,
                           {"final_response": "2"}, ACCEPT]
                job_id, job, _ = guidance.StarGuidanceTest.run_public(
                    self, replies, SHOWCASE_STAR_REGISTRY=registry,
                    SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                        max_model_calls=18, max_http_attempts=18, max_tool_calls=quota))
                self.assertEqual("succeeded", job["status"], job)
                reasoner = next(r for r in self.outbound if r["role"] == "reason_noncoding")
                self.assertEqual([], reasoner["allowed_tools"])
                verifier = next(r for r in self.outbound if r["role"] == "step_verifier")
                self.assertEqual(["polynomial_check"] if quota else [], verifier["allowed_tools"])
                self.assertEqual([1] if quota else [], actual)
                self.assertEqual(quota, self.report(job_id)["budget"]["tool_calls"])
                receipts = [x["receipt"] for x in job["result"]["tool_results"]]
                self.assertTrue(any(r.get("reason") == "pure_reasoning_denied" for r in receipts))
                self.assertTrue(any(r.get("status") == "success" if quota else
                                    r.get("reason") == "tool_call_budget_exhausted" for r in receipts))
