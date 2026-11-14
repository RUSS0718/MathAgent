"""Generated formal targets retain task ownership and public requirement failures."""

import unittest
from copy import deepcopy

from showcase.formal import LeanTacticProver
from showcase.run_budget import RunBudgetLimits
from showcase.solver_harness import ScriptedVerifierPort, SolverHarness
from tests.star_product_support import StarJobFixture
from tests.test_faithful_auto_intake import (
    ACCEPT,
    CONFIG,
    POLISH,
    PROBLEM,
    SOLVED,
    SPEC,
    IntakePort,
)
from tests.test_faithful_s09_public_job import POLICY, TARGET, FakeTransport
from tests.test_faithful_s09_public_job import SPEC as RATIONAL_SPEC


class FormalGenerationTest(unittest.TestCase):
    def test_intake_persists_generated_choice_without_extra_call(self):
        reply = deepcopy(SPEC)
        reply["formalization"] = {"status": "unsupported", "reason": "real root enumeration", "require_formal": True, "obligation_ids": [], "target": None}
        port = IntakePort([reply, SOLVED, POLISH])
        with SolverHarness(config=CONFIG, model_port=port, verifier_port=ScriptedVerifierPort([ACCEPT])) as harness:
            run = harness.solve(PROBLEM, {"run_id": "formal-generation"})
        selection = run["state"]["formalization"]
        self.assertEqual("unsupported", selection["status"])
        self.assertTrue(selection["require_formal"])
        self.assertEqual(3, len(port.requests))
        self.assertEqual("formal-generation:problem-intake:1", selection["source"]["generation_call_id"])


class GeneratedFormalPublicTest(StarJobFixture, unittest.TestCase):
    def test_ordinary_input_freezes_policy_or_keeps_required_unsupported(self):
        for supported in (True, False):
            with self.subTest(supported=supported):
                spec = deepcopy(RATIONAL_SPEC)
                if not supported:
                    spec["domain"] = "reals"
                spec["formalization"] = {
                    "status": "proposed", "reason": "identity", "require_formal": True,
                    "obligation_ids": ["root:identity"], "target": {
                        k: v for k, v in TARGET.items() if k not in {"hash", "_lean_lhs", "_lean_rhs"}},
                }
                transport = FakeTransport()
                self.open_star([spec, SOLVED, POLISH, ACCEPT],
                    SHOWCASE_STAR_FEATURES={"auto_problem_spec": True, "problem_spec": True,
                        "final_generation": True, "final_solution_review": True},
                    SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8,max_http_attempts=8,max_tool_calls=2),
                    SHOWCASE_FORMAL_GENERATION_REQUIRED=True,
                    SHOWCASE_FORMAL_BACKEND=LeanTacticProver(transport),
                    SHOWCASE_FORMAL_VERIFICATION_CONFIG=POLICY)
                response = self.client.post("/api/agent/jobs", json={
                    "message": spec["original_problem"], "session_id": self.session,
                    "solver_mode": "star_limited"}, headers=self.headers())
                self.assertEqual(202, response.status_code, response.get_json())
                job_id = response.get_json()["job_id"]
                job = self.terminal(job_id)
                result = job["result"]
                self.assertEqual(POLISH["solution_candidate"], result["final_response"])
                self.assertEqual("failed", job["status"])
                self.assertEqual("needs_review", result["solver"]["semantics"]["execution"])
                formal = result["formal_verification"]
                self.assertEqual("unmet", formal["assessment"]["status"])
                self.assertIn("schema_version", formal)
                service = self.app.extensions["showcase_workspace_service"]
                if supported:
                    identity = service.store.job_identity(job_id)
                    self.assertIn("source", identity["formal_policy"])
                    self.assertEqual(1, len(transport.calls))
                else:
                    self.assertEqual("unsupported", formal["status"])
                    self.assertEqual([], transport.calls)
                self.assertEqual(4, self.post.call_count)
