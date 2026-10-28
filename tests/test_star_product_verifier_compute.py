"""Verifier-initiated controlled computation through the public STAR Job entry."""

import json
import os
import unittest

from showcase.run_budget import RunBudgetLimits
from showcase.tools import ToolRegistry
from tests.star_product_support import ACCEPT, POLISH, SOLVED, StarJobFixture

IMAGE = os.environ.get("MATHAGENT_TEST_PYTHON_IMAGE")

NEED_PLAN = {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []}
PLAN = {"version": 1, "steps": [{"step_id": "sum", "title": "Add", "objective": "Compute 1+1"}]}
STEP = {"argument": "addition", "blocked": False, "claims": [
    {"statement": "1+1=2 for every carrier", "label": "hard-verify"}]}
REQUEST = {"tool": "polynomial_check", "arguments": {"coefficients": [1]},
           "scope": "finite_computation", "expected_output": 2}
# The first review replies ACCEPT together with its own computation request:
# acceptance must never be parsed before the requested computation completed.
PREMATURE = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": "",
             "tool_request": REQUEST}
CONTINUE = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
            "objection": "Substitution checked by isolated computation."}
FEATURES = {"final_generation": True, "final_solution_review": True, "local_code_tool": True}


class StarVerifierComputeTest(StarJobFixture, unittest.TestCase):
    def solver_events(self, job_id):
        text = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        events = []
        for line in text.splitlines():
            if line.startswith("data: "):
                data = json.loads(line[6:])
                if data.get("solver_event_type"):
                    events.append((data["solver_event_type"], data.get("solver_revision")))
        return events

    def test_step_verifier_request_executes_and_continues_review(self):
        from showcase.run_budget import current_budget

        actual = []
        registry = ToolRegistry()
        registry.register(
            "polynomial_check", lambda args: actual.append(current_budget().run_id) or 2)
        self.open_star(
            [NEED_PLAN, PLAN, STEP, PREMATURE, CONTINUE, {"final_response": "1+1=2"}, ACCEPT],
            SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                max_model_calls=10, max_http_attempts=10, max_tool_calls=4),
            SHOWCASE_STAR_REGISTRY=registry)
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual([job_id], actual)
        self.assertEqual(1, self.report(job_id)["budget"]["tool_calls"])
        reviews = [context for context in self.outbound if context["role"] == "step_verifier"]
        self.assertEqual(2, len(reviews), self.outbound)
        first, continuation = reviews
        self.assertIn("polynomial_check", first["allowed_tools"])
        receipts = continuation["report"]["tool_receipts"]
        self.assertEqual(1, len(receipts))
        receipt = receipts[0]
        self.assertEqual("step_verifier", receipt["source_role"])
        self.assertEqual("success", receipt["status"])
        self.assertTrue(receipt["executed"])
        self.assertEqual(2, receipt["output"])
        self.assertEqual({"coefficients": [1]}, receipt["input"])
        self.assertTrue(receipt["review_call_id"].startswith(first["call_id"]))
        public = job["result"]["tool_results"]
        self.assertEqual(
            [receipt["receipt_id"]],
            [item["tool_call_id"] for item in public if item["receipt"].get("source_role")
             == "step_verifier"])
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        self.assertIn(receipt["receipt_id"], [item.get("tool_call_id") for item in evidence["tools"]])
        report = self.report(job_id)
        self.assertIn(receipt["receipt_id"],
                      [item.get("tool_call_id") for item in report["tool_summaries"]])
        self.assertEqual(
            "Finite computation only; not a completeness proof",
            next(item["result_summary"] for item in report["tool_summaries"]
                 if item["tool_call_id"] == receipt["receipt_id"]))
        events = self.solver_events(job_id)
        kinds = [kind for kind, _ in events]
        self.assertIn("tool_dispatched", kinds)
        self.assertIn("tool_receipt", kinds)
        reviewed = [revision for kind, revision in events if kind == "step_reviewed"]
        self.assertEqual(1, len(reviewed), events)
        receipt_revision = next(revision for kind, revision in events if kind == "tool_receipt")
        self.assertLess(receipt_revision, reviewed[0])

    def test_verifier_independently_recomputes_an_easy_verify_claim(self):
        """AC-05: easy-verify supports independent execution or an independent
        recomputation. The precheck already ran the claim's own request; the
        reviewer then picks its own check of the same claim and the recomputed
        receipt — not the Reasoner's — is what its continuation sees."""
        from showcase.run_budget import current_budget

        actual = []
        registry = ToolRegistry()
        registry.register(
            "polynomial_check", lambda args: actual.append(args) or 2)
        easy_claim = {
            "argument": "substitution", "blocked": False, "claims": [{
                "statement": "1+1=2", "label": "easy-verify",
                "tool_request": {"tool": "polynomial_check", "arguments": {"coefficients": [1]},
                                 "scope": "finite_computation", "expected_output": 2}}]}
        # A different argument set: the reviewer recomputes instead of trusting.
        independent = {"tool": "polynomial_check", "arguments": {"coefficients": [2]},
                       "scope": "finite_computation", "expected_output": 2}
        first_review = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
                        "objection": "", "tool_request": independent}
        second_review = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
                         "objection": "Independent recomputation agrees."}
        self.open_star([NEED_PLAN, PLAN, easy_claim, first_review, second_review,
                        {"final_response": "2"}, ACCEPT],
            SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                max_model_calls=10, max_http_attempts=10, max_tool_calls=4),
            SHOWCASE_STAR_REGISTRY=registry)
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        # Two real executions: the claim's own precheck and the reviewer's own check.
        self.assertEqual([{"coefficients": [1]}, {"coefficients": [2]}], actual)
        reviews = [context for context in self.outbound if context["role"] == "step_verifier"]
        self.assertEqual(2, len(reviews), self.outbound)
        receipt = reviews[1]["report"]["tool_receipts"][-1]
        self.assertEqual("step_verifier", receipt["source_role"])
        self.assertEqual("success", receipt["status"])
        self.assertEqual({"coefficients": [2]}, receipt["input"])
        self.assertEqual(2, self.report(job_id)["budget"]["tool_calls"])

    def test_whole_solution_verifier_request_executes_and_continues_review(self):
        from showcase.run_budget import current_budget

        actual = []
        registry = ToolRegistry()
        registry.register(
            "polynomial_check", lambda args: actual.append(current_budget().run_id) or 2)
        whole_request = {"verdict": "ACCEPT", "reason": "", "tool_request": REQUEST}
        self.open_star([SOLVED, POLISH, whole_request, {"verdict": "ACCEPT", "reason": "checked"}],
            SHOWCASE_STAR_FEATURES={"local_code_tool": True},
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                max_model_calls=8, max_http_attempts=8, max_tool_calls=4),
            SHOWCASE_STAR_REGISTRY=registry)
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual([job_id], actual)
        reviews = [context for context in self.outbound if context["role"] == "whole_solution_verifier"]
        self.assertEqual(2, len(reviews), self.outbound)
        receipt = reviews[1]["report"]["tool_receipts"][0]
        self.assertEqual("whole_solution_verifier", receipt["source_role"])
        self.assertEqual("success", receipt["status"])
        self.assertEqual(2, receipt["output"])
        self.assertEqual(1, self.report(job_id)["budget"]["tool_calls"])

    def test_tool_ceiling_allows_verifier_continuation_and_answer(self):
        executed = []
        registry = ToolRegistry()
        registry.register("polynomial_check", lambda args: executed.append(args) or 2)
        self.open_star(
            [NEED_PLAN, PLAN, STEP, PREMATURE, CONTINUE, {"final_response": "1+1=2"}, ACCEPT],
            SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                max_model_calls=12, max_http_attempts=12, max_tool_calls=1),
            SHOWCASE_STAR_REGISTRY=registry)
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual("1+1=2", job["result"]["final_response"])
        self.assertEqual(1, len(executed))
        self.assertEqual(1, self.report(job_id)["budget"]["tool_calls"])
        reviews = [context for context in self.outbound if context["role"] == "step_verifier"]
        self.assertEqual(2, len(reviews), [c["role"] for c in self.outbound])
        self.assertEqual([], reviews[1]["allowed_tools"])
        self.assertEqual("same_artifact", self.report(job_id)["semantics"]["binding"])
        public = job["result"]["tool_results"]
        self.assertEqual(["success"], [item["status"] for item in public])
        reviewed = [event for event in self.solver_events(job_id)
                    if event[0] == "step_reviewed"]
        self.assertEqual(1, len(reviewed), self.solver_events(job_id))

    def test_cancel_during_verifier_tool_prevents_continuation(self):
        import threading

        from showcase.run_budget import current_budget

        entered, release, returned = threading.Event(), threading.Event(), threading.Event()
        self.addCleanup(release.set)
        actual = []
        registry = ToolRegistry()

        def handler(args):
            actual.append(current_budget().run_id)
            entered.set()
            release.wait(5)
            returned.set()
            return 2

        registry.register("polynomial_check", handler)
        self.open_star([NEED_PLAN, PLAN, STEP, PREMATURE], SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=10, max_http_attempts=10),
            SHOWCASE_STAR_REGISTRY=registry)
        job_id = self.create_job()
        self.assertTrue(entered.wait(5))
        self.cancel(job_id)
        release.set()
        self.assertTrue(returned.wait(5))
        self.wait_for(lambda: "late_result" in self.client.get(
            f"/api/agent/jobs/{job_id}/events").get_data(as_text=True))
        self.assertEqual([job_id], actual)
        self.assertEqual(4, len(self.outbound))
        self.assertEqual("canceled", self.job(job_id)["status"])
        self.assertEqual(1, self.report(job_id)["budget"]["tool_calls"])

    def test_final_whole_review_executes_its_own_request_in_plan_mode(self):
        from showcase.run_budget import current_budget

        actual = []
        registry = ToolRegistry()
        registry.register(
            "polynomial_check", lambda args: actual.append(current_budget().run_id) or 2)
        whole_request = {"verdict": "ACCEPT", "reason": "", "tool_request": REQUEST}
        self.open_star(
            [NEED_PLAN, PLAN, STEP, PREMATURE, CONTINUE, {"final_response": "1+1=2"},
             whole_request, {"verdict": "ACCEPT", "reason": "checked"}],
            SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                max_model_calls=12, max_http_attempts=12, max_tool_calls=4),
            SHOWCASE_STAR_REGISTRY=registry)
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual([job_id, job_id], actual)
        reviews = [context for context in self.outbound
                   if context["role"] == "whole_solution_verifier"]
        self.assertEqual(2, len(reviews), [c["role"] for c in self.outbound])
        receipt = reviews[1]["report"]["tool_receipts"][0]
        self.assertEqual("whole_solution_verifier", receipt["source_role"])
        self.assertEqual("success", receipt["status"])
        self.assertEqual(2, self.report(job_id)["budget"]["tool_calls"])


@unittest.skipUnless(IMAGE, "requires independently validated local Docker image ID")
class StarFullReferenceVerifierComputeTest(StarJobFixture, unittest.TestCase):
    def solver_events(self, job_id):
        text = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        events = []
        for line in text.splitlines():
            if line.startswith("data: "):
                data = json.loads(line[6:])
                if data.get("solver_event_type"):
                    events.append((data["solver_event_type"], data.get("solver_revision")))
        return events

    def test_reference_step_verifier_executes_own_isolated_computation(self):
        code = "import sympy as sp\nx=sp.symbols('x')\nprint(sp.factor(x**2-1))"
        expected = "(x - 1)*(x + 1)\n"
        premature = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
                     "objection": "", "tool_request": {
                         "tool": "python_math", "arguments": {"code": code},
                         "scope": "finite_computation", "expected_output": expected}}
        self.open_star(
            [NEED_PLAN, PLAN, STEP, premature, CONTINUE,
             {"final_response": "x^2 - 1 = (x - 1)(x + 1)."}, ACCEPT],
            SHOWCASE_STAR_FULL_ENABLED=True, SHOWCASE_STAR_PYTHON_IMAGE_ID=IMAGE)
        response = self.client.post("/api/agent/jobs", json={
            "message": "Factor x^2-1.", "session_id": self.session,
            "solver_mode": "star_reference"}, headers=self.headers())
        self.assertEqual(202, response.status_code, response.get_json())
        job_id = response.get_json()["job_id"]
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual("star_reference", job["result"]["execution_mode"])
        self.assertEqual([], job["result"]["missing_capabilities"])
        reviews = [context for context in self.outbound if context["role"] == "step_verifier"]
        self.assertEqual(2, len(reviews), [c["role"] for c in self.outbound])
        receipt = reviews[1]["report"]["tool_receipts"][0]
        self.assertEqual("step_verifier", receipt["source_role"])
        self.assertEqual("success", receipt["status"])
        self.assertTrue(receipt["executed"])
        self.assertTrue(receipt["cleanup_verified"])
        self.assertEqual(IMAGE, receipt["image"])
        self.assertEqual(expected, receipt["output"])
        self.assertTrue(receipt["assertion_matched"])
        # The verifier's own code and stdout resolve through the public artifact seam.
        resolved = self.client.get(
            f"/api/agent/jobs/{job_id}/artifacts/{receipt['code_ref']['sha256']}")
        self.assertEqual(200, resolved.status_code)
        self.assertEqual(code.encode("utf-8"), resolved.data)
        stdout = self.client.get(
            f"/api/agent/jobs/{job_id}/artifacts/{receipt['stdout_ref']['sha256']}")
        self.assertEqual(expected.encode("utf-8"), stdout.data)
        report = self.report(job_id)
        self.assertEqual(7, report["budget"]["logical_calls"])
        self.assertEqual(1, report["budget"]["tool_calls"])
        events = self.solver_events(job_id)
        reviewed = [revision for kind, revision in events if kind == "step_reviewed"]
        self.assertEqual(1, len(reviewed), events)
        receipt_revision = next(revision for kind, revision in events if kind == "tool_receipt")
        self.assertLess(receipt_revision, reviewed[0])


if __name__ == "__main__":
    unittest.main()
