"""Verifier-initiated controlled computation through the public STAR Job entry."""

import json
import unittest

from showcase.run_budget import RunBudgetLimits
from showcase.tools import ToolRegistry
from tests.star_product_support import ACCEPT, POLISH, SOLVED, StarJobFixture

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

    def test_tool_budget_exhaustion_stops_further_verifier_dispatch(self):
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
        self.assertEqual("failed", job["status"], job)
        self.assertEqual("partial_budget_exhausted", job["result"]["solver"]["status"])
        self.assertIn("Hard budget exhausted", job["result"]["final_response"])
        self.assertEqual(1, len(executed))
        self.assertEqual(1, self.report(job_id)["budget"]["tool_calls"])
        reviews = [context for context in self.outbound if context["role"] == "step_verifier"]
        self.assertEqual(1, len(reviews), [c["role"] for c in self.outbound])
        public = job["result"]["tool_results"]
        self.assertEqual(["success"], [item["status"] for item in public])
        reviewed = [event for event in self.solver_events(job_id)
                    if event[0] == "step_reviewed"]
        self.assertEqual([], reviewed, self.solver_events(job_id))

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


if __name__ == "__main__":
    unittest.main()
