"""Explore-initiated controlled computation through the public STAR Job entry.

The Explore role was fixed as computation-free exploration: its reply schema had
no tool_request field and its role never received allowed_tools. These cases
walk the authenticated public Job with a real ToolRegistry so a declared finite
enumeration is actually executed through the shared S3 path, the receipt
continues the same exploration session, and the computed output with its source
reaches the Planner's actual request while every exploration result keeps its
unverified_exploration identity.
"""

import json
import os
import unittest

from showcase.run_budget import RunBudgetLimits
from showcase.tools import ToolRegistry
from tests.star_product_support import ACCEPT, POLISH, SOLVED, StarJobFixture

IMAGE = os.environ.get("MATHAGENT_TEST_PYTHON_IMAGE")

REQUEST = {"tool": "polynomial_check", "arguments": {"coefficients": [1]},
           "scope": "finite_computation", "expected_output": 2}
# The first exploration proposes its own finite enumeration while claiming
# SOLVED: the assessment in this reply must not be parsed before the requested
# computation actually ran and a continuation reply was issued.
ENUMERATE = {"assessment": "SOLVED", "worked": ["small cases"], "failed": [],
             "candidates": [], "solution_candidate": "2", "tool_request": REQUEST}
CONTINUE = {"assessment": "SOLVED", "worked": ["enumeration executed"], "failed": [],
            "candidates": [], "solution_candidate": "1+1=2"}
NEED_PLAN = {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []}
PLAN = {"version": 1, "steps": [{"step_id": "sum", "title": "Add", "objective": "Compute 1+1"}]}
STEP = {"argument": "addition", "blocked": False, "claims": [
    {"statement": "1+1=2 for every carrier", "label": "hard-verify"}]}
STEP_VERDICT = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": ""}
FEATURES = {"local_code_tool": True}
PLAN_FEATURES = {"final_generation": True, "final_solution_review": True, "local_code_tool": True}
BUDGET = RunBudgetLimits(max_model_calls=12, max_http_attempts=12, max_tool_calls=4)


class StarExploreComputeTest(StarJobFixture, unittest.TestCase):
    def solver_events(self, job_id):
        text = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        events = []
        for line in text.splitlines():
            if line.startswith("data: "):
                data = json.loads(line[6:])
                if data.get("solver_event_type"):
                    events.append((data["solver_event_type"], data.get("solver_revision")))
        return events

    def test_explore_request_executes_and_continues_exploration(self):
        from showcase.run_budget import current_budget

        actual = []
        registry = ToolRegistry()
        registry.register(
            "polynomial_check", lambda args: actual.append(current_budget().run_id) or 2)
        self.open_star(
            [ENUMERATE, CONTINUE, POLISH, ACCEPT],
            SHOWCASE_STAR_FEATURES=FEATURES, SHOWCASE_STAR_BUDGET=BUDGET,
            SHOWCASE_STAR_REGISTRY=registry)
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual([job_id], actual)
        self.assertEqual(1, self.report(job_id)["budget"]["tool_calls"])
        explores = [context for context in self.outbound if context["role"] == "explore"]
        self.assertEqual(2, len(explores), self.outbound)
        first, continuation = explores
        self.assertIn("polynomial_check", first["allowed_tools"])
        receipts = continuation["report"]["tool_receipts"]
        self.assertEqual(1, len(receipts))
        receipt = receipts[0]
        self.assertEqual("explore", receipt["source_role"])
        self.assertEqual("success", receipt["status"])
        self.assertTrue(receipt["executed"])
        self.assertEqual(2, receipt["output"])
        self.assertEqual({"coefficients": [1]}, receipt["input"])
        self.assertTrue(receipt["receipt_id"].startswith("explore-tool:"))
        self.assertEqual(f"{first['call_id']}:tool-1", continuation["call_id"])
        # A claimed SOLVED together with a pending request never ends the run:
        # polish and a new whole-solution review still happen after the tool.
        self.assertEqual(
            ["explore", "explore", "explore_polish", "whole_solution_verifier"],
            [context["role"] for context in self.outbound])
        public = job["result"]["tool_results"]
        self.assertEqual(
            [receipt["receipt_id"]],
            [item["tool_call_id"] for item in public if item["receipt"].get("source_role")
             == "explore"])
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
        reviewed = [revision for kind, revision in events if kind == "solution_review_assessed"]
        self.assertEqual(1, len(reviewed), events)
        receipt_revision = next(revision for kind, revision in events if kind == "tool_receipt")
        self.assertLess(receipt_revision, reviewed[0])

    def test_explore_counterexample_computation_reaches_planner_request(self):
        counter = {"found": True, "counterexample": "n=3", "violated": "every n is odd"}
        registry = ToolRegistry()
        registry.register("polynomial_check", lambda args: counter)
        probe = {**ENUMERATE, "tool_request":
                 {**REQUEST, "arguments": {"coefficients": [3]}, "expected_output": counter}}
        finding_reply = {**NEED_PLAN, "candidates": ["computed counterexample n=3"]}
        self.open_star(
            [probe, finding_reply, PLAN, STEP, STEP_VERDICT, {"final_response": "1+1=2"}, ACCEPT],
            SHOWCASE_STAR_FEATURES=PLAN_FEATURES, SHOWCASE_STAR_BUDGET=BUDGET,
            SHOWCASE_STAR_REGISTRY=registry)
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        planner = next(context for context in self.outbound if context["role"] == "planner")
        finding = planner["exploration_findings"][0]
        self.assertEqual("NEED_PLAN", finding["assessment"])
        self.assertEqual("unverified_exploration", finding["provenance"])
        computation = finding["computation"]
        self.assertEqual("unverified_exploration", computation["provenance"])
        self.assertEqual("finite_computation", computation["scope"])
        self.assertEqual(counter, computation["receipts"][0]["output"])
        # The computed counterexample is an unverified exploration result: the
        # proven-ledger fields stay empty and no evidence grade was minted.
        self.assertEqual([], planner["role_context"]["state"]["accepted_results"])
        self.assertEqual([], planner["role_context"]["state"]["verified_results_ledger"])
        self.assertNotIn("label", computation["receipts"][0])
        self.assertNotIn("evidence_level", computation["receipts"][0])

    def test_explore_computation_mismatch_is_recorded_honestly(self):
        actual = []
        registry = ToolRegistry()
        registry.register("polynomial_check", lambda args: actual.append(1) or 2)
        probe = {**ENUMERATE, "tool_request": {**REQUEST, "expected_output": 5}}
        finding_reply = {**NEED_PLAN, "failed": ["enumeration did not match the expectation"]}
        self.open_star(
            [probe, finding_reply, PLAN, STEP, STEP_VERDICT, {"final_response": "1+1=2"}, ACCEPT],
            SHOWCASE_STAR_FEATURES=PLAN_FEATURES, SHOWCASE_STAR_BUDGET=BUDGET,
            SHOWCASE_STAR_REGISTRY=registry)
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual(1, len(actual))
        planner = next(context for context in self.outbound if context["role"] == "planner")
        computed = planner["exploration_findings"][0]["computation"]["receipts"][0]
        self.assertEqual("success", computed["status"])
        self.assertFalse(computed["assertion_matched"])
        self.assertEqual(2, computed["output"])
        # A mismatched sample is still only an unverified exploration fact.
        self.assertEqual([], planner["role_context"]["state"]["accepted_results"])
        public = job["result"]["tool_results"]
        self.assertEqual(["success"], [item["status"] for item in public])
        self.assertEqual(
            ["Finite computation only; not a completeness proof"],
            [item["result_summary"] for item in public])

    def test_simple_problem_keeps_the_fast_track_without_tools(self):
        executed = []
        registry = ToolRegistry()
        registry.register("polynomial_check", lambda args: executed.append(args) or 2)
        self.open_star([SOLVED, POLISH, ACCEPT],
            SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                max_model_calls=8, max_http_attempts=8, max_tool_calls=4),
            SHOWCASE_STAR_REGISTRY=registry)
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual([], executed)
        self.assertEqual(0, self.report(job_id)["budget"]["tool_calls"])
        self.assertEqual(
            ["explore", "explore_polish", "whole_solution_verifier"],
            [context["role"] for context in self.outbound])

    def test_repeated_explore_request_is_unfulfilled_and_never_parsed(self):
        actual = []
        registry = ToolRegistry()
        registry.register("polynomial_check", lambda args: actual.append(1) or 2)
        self.open_star(
            [ENUMERATE, ENUMERATE, PLAN, STEP, STEP_VERDICT, {"final_response": "1+1=2"}, ACCEPT],
            SHOWCASE_STAR_FEATURES=PLAN_FEATURES, SHOWCASE_STAR_BUDGET=BUDGET,
            SHOWCASE_STAR_REGISTRY=registry)
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual(1, len(actual))
        self.assertEqual(1, self.report(job_id)["budget"]["tool_calls"])
        explores = [context for context in self.outbound if context["role"] == "explore"]
        self.assertEqual(2, len(explores), self.outbound)
        # The assessment of the repeated request was discarded; the run went to
        # the Planner instead of polishing an unverified quick answer.
        planner = next(context for context in self.outbound if context["role"] == "planner")
        finding = planner["exploration_findings"][0]
        self.assertEqual("UNKNOWN", finding["assessment"])
        self.assertEqual("explore_tool_request_unfulfilled", finding["computation"]["unfulfilled"])
        self.assertEqual(
            ["explore", "explore", "planner", "reasoner", "step_verifier",
             "final_generator", "whole_solution_verifier"],
            [context["role"] for context in self.outbound])

    def test_cancel_during_explore_tool_prevents_continuation(self):
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
        self.open_star([ENUMERATE], SHOWCASE_STAR_FEATURES=FEATURES,
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
        self.assertEqual(1, len(self.outbound))
        self.assertEqual("canceled", self.job(job_id)["status"])
        self.assertEqual(1, self.report(job_id)["budget"]["tool_calls"])


@unittest.skipUnless(IMAGE, "requires independently validated local Docker image ID")
class StarFullReferenceExploreComputeTest(StarJobFixture, unittest.TestCase):
    def solver_events(self, job_id):
        text = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        events = []
        for line in text.splitlines():
            if line.startswith("data: "):
                data = json.loads(line[6:])
                if data.get("solver_event_type"):
                    events.append((data["solver_event_type"], data.get("solver_revision")))
        return events

    def test_reference_explore_executes_own_isolated_computation(self):
        code = "print([i * i for i in range(4)])"
        expected = "[0, 1, 4, 9]\n"
        probe = {**ENUMERATE, "tool_request": {
            "tool": "python_math", "arguments": {"code": code},
            "scope": "finite_computation", "expected_output": expected}}
        self.open_star(
            [probe, CONTINUE, POLISH, ACCEPT],
            SHOWCASE_STAR_FULL_ENABLED=True, SHOWCASE_STAR_PYTHON_IMAGE_ID=IMAGE)
        response = self.client.post("/api/agent/jobs", json={
            "message": "Enumerate the first squares.", "session_id": self.session,
            "solver_mode": "star_reference"}, headers=self.headers())
        self.assertEqual(202, response.status_code, response.get_json())
        job_id = response.get_json()["job_id"]
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual("star_reference", job["result"]["execution_mode"])
        self.assertEqual([], job["result"]["missing_capabilities"])
        explores = [context for context in self.outbound if context["role"] == "explore"]
        self.assertEqual(2, len(explores), [c["role"] for c in self.outbound])
        receipt = explores[1]["report"]["tool_receipts"][0]
        self.assertEqual("explore", receipt["source_role"])
        self.assertEqual("success", receipt["status"])
        self.assertTrue(receipt["executed"])
        self.assertTrue(receipt["cleanup_verified"])
        self.assertEqual(IMAGE, receipt["image"])
        self.assertEqual(expected, receipt["output"])
        self.assertTrue(receipt["assertion_matched"])
        # The exploration's own code and stdout resolve through the public seam.
        resolved = self.client.get(
            f"/api/agent/jobs/{job_id}/artifacts/{receipt['code_ref']['sha256']}")
        self.assertEqual(200, resolved.status_code)
        self.assertEqual(code.encode("utf-8"), resolved.data)
        stdout = self.client.get(
            f"/api/agent/jobs/{job_id}/artifacts/{receipt['stdout_ref']['sha256']}")
        self.assertEqual(expected.encode("utf-8"), stdout.data)
        report = self.report(job_id)
        self.assertEqual(1, report["budget"]["tool_calls"])
        events = self.solver_events(job_id)
        reviewed = [revision for kind, revision in events if kind == "solution_review_assessed"]
        self.assertEqual(1, len(reviewed), events)
        receipt_revision = next(revision for kind, revision in events if kind == "tool_receipt")
        self.assertLess(receipt_revision, reviewed[0])


if __name__ == "__main__":
    unittest.main()
