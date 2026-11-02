"""Trusted preset bounds observed through authenticated Jobs, never HTTP options."""

import unittest

from showcase.run_budget import RunBudgetLimits
from showcase.tools import ToolRegistry
from tests.star_product_support import ACCEPT, POLISH, SOLVED, RawProviderContent, StarJobFixture
from tests.test_star_product_verifier_compute import (
    CONTINUE, FEATURES, NEED_PLAN, PLAN, PREMATURE, REQUEST, STEP,
)


class StarComputeBoundsTest(StarJobFixture, unittest.TestCase):
    def wait_for(self, predicate):
        import time

        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if value := predicate():
                return value
            time.sleep(.01)
        self.fail("public STAR observation timed out")

    def open_bounded(self, replies, value, *, tool_limit=8):
        self.executed = []
        registry = ToolRegistry()

        def execute(arguments):
            self.executed.append(arguments)
            return 2

        registry.register("polynomial_check", execute)
        self.open_star(replies, SHOWCASE_STAR_FEATURES=FEATURES,
                       SHOWCASE_STAR_REGISTRY=registry,
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                           max_model_calls=24, max_http_attempts=24,
                           max_tool_calls=tool_limit))
        # Existing trusted server preset; no new Flask/HTTP configuration API.
        preset = self.app.extensions["showcase_workspace_service"].star_pipeline.config
        if value != "missing":
            preset["max_verifier_tool_requests"] = value

    def request(self, number, role):
        request = {**REQUEST, "arguments": {"coefficients": [number]}}
        if role == "explore":
            return {**SOLVED, "tool_request": request}
        if role == "whole_solution_verifier":
            return {**ACCEPT, "tool_request": request}
        return {**PREMATURE, "tool_request": request}

    def bounded_case(self, value, expected, role):
        requests = [self.request(index + 1, role) for index in range(expected + 1)]
        prefix = [] if role == "explore" else (
            [SOLVED, POLISH] if role == "whole_solution_verifier" else [NEED_PLAN, PLAN, STEP])
        suffix = [] if role == "step_verifier" else [RawProviderContent("{}"), RawProviderContent("{}")]
        self.open_bounded([*prefix, *requests, *suffix], value)
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual([{"coefficients": [index + 1]} for index in range(expected)],
                         self.executed)
        outbound = [item for item in self.outbound if item["role"] == role]
        self.assertEqual(expected + 1, len(outbound), self.outbound)
        for index, item in enumerate(outbound[1:]):
            receipt = item["report"]["tool_receipts"][-1]
            self.assertTrue(receipt["executed"])
            self.assertEqual("success", receipt["status"])
            self.assertEqual(2, receipt["output"])
            self.assertEqual({"coefficients": [index + 1]}, receipt["input"])
        self.assertNotEqual("succeeded", job["status"], job)
        self.assertEqual(expected, self.report(job_id)["budget"]["tool_calls"])
        # Explore/fast-path rejection legitimately falls back to Planner. Stop at
        # that boundary with a known invalid reply plus its one bounded repair.
        extra = 0 if role == "step_verifier" else 2
        self.assertEqual(len(prefix) + expected + 1 + extra, self.post.call_count)
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        tools = evidence["tools"]
        self.assertEqual(expected, len(tools), tools)

    def test_zero_step_review_does_not_execute_or_accept_pending_request(self):
        self.bounded_case(0, 0, "step_verifier")

    def test_one_step_review_executes_once(self):
        self.bounded_case(1, 1, "step_verifier")

    def test_default_step_review_executes_twice(self):
        self.bounded_case("missing", 2, "step_verifier")

    def test_explicit_default_executes_twice(self):
        self.bounded_case(2, 2, "step_verifier")

    def test_negative_falls_back_to_two(self):
        self.bounded_case(-1, 2, "step_verifier")

    def test_seventeen_falls_back_to_two(self):
        self.bounded_case(17, 2, "step_verifier")

    def test_bool_falls_back_to_two(self):
        self.bounded_case(True, 2, "step_verifier")

    def test_false_falls_back_to_two_not_zero(self):
        self.bounded_case(False, 2, "step_verifier")

    def test_string_falls_back_to_two(self):
        self.bounded_case("1", 2, "step_verifier")

    def test_zero_explore_does_not_execute_or_accept_pending_request(self):
        self.bounded_case(0, 0, "explore")

    def test_one_explore_executes_once(self):
        self.bounded_case(1, 1, "explore")

    def test_default_explore_executes_twice(self):
        self.bounded_case("missing", 2, "explore")

    def test_zero_whole_review_does_not_accept_pending_request(self):
        self.bounded_case(0, 0, "whole_solution_verifier")

    def test_one_whole_review_executes_once(self):
        self.bounded_case(1, 1, "whole_solution_verifier")

    def test_distinct_review_scopes_each_allow_one_real_execution(self):
        self.open_bounded([NEED_PLAN, PLAN, STEP, PREMATURE, CONTINUE,
                           {"final_response": "1+1=2"},
                           self.request(2, "whole_solution_verifier"), ACCEPT], 1)
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual("1+1=2", job["result"]["final_response"])
        self.assertEqual([{"coefficients": [1]}, {"coefficients": [2]}], self.executed)
        for role in ("step_verifier", "whole_solution_verifier"):
            reviews = [item for item in self.outbound if item["role"] == role]
            self.assertEqual(2, len(reviews))
            receipts = [item for item in reviews[-1]["report"]["tool_receipts"]
                        if item["source_role"] == role]
            self.assertEqual(1, len(receipts))
            self.assertTrue(receipts[0]["executed"])
            self.assertEqual(2, receipts[0]["output"])
        self.assertEqual(reviews[-1]["call_id"],
                         self.report(job_id)["checks"]["source"]["call_id"])
        self.assertEqual(8, self.post.call_count)
        self.assertEqual(2, self.report(job_id)["budget"]["tool_calls"])
        self.assertEqual(2, len(self.client.get(
            f"/api/runs/{job_id}/evidence").get_json()["tools"]))

    def test_whole_review_source_follows_computation_and_format_repair(self):
        for path in ("explore", "final"):
            for order in ("tool", "repair-tool", "tool-repair"):
                with self.subTest(path=path, order=order):
                    prefix = [SOLVED, POLISH] if path == "explore" else [
                        NEED_PLAN, PLAN, STEP, CONTINUE, {"final_response": "1+1=2"}]
                    request = self.request(2, "whole_solution_verifier")
                    replies = {"tool": [request, ACCEPT],
                               "repair-tool": [RawProviderContent("{"), request, ACCEPT],
                               "tool-repair": [request, RawProviderContent("{"), ACCEPT]}[order]
                    self.open_bounded([*prefix, *replies], 1)
                    job_id = self.create_job()
                    job = self.terminal(job_id)
                    # The fast review deliberately does not repair a malformed
                    # tool continuation: it must not promote the pending request.
                    if path == "explore" and order == "tool-repair":
                        self.assertNotEqual("succeeded", job["status"])
                    else:
                        self.assertEqual("succeeded", job["status"], job)
                        reviews = [r for r in self.outbound
                                   if r["role"] == "whole_solution_verifier"]
                        self.assertEqual(reviews[-1]["call_id"], self.report(job_id)[
                            "checks"]["source"]["call_id"])
                        self.assertEqual(2, reviews[-1]["report"]["tool_receipts"][-1]["output"])
                        self.assertEqual("llm_whole_review_accepted", self.report(job_id)[
                            "checks"]["findings"][0])
                    self.assertEqual([{"coefficients": [2]}], self.executed)
                    # Close each fixture before opening the next subcase.
                    self.doCleanups()

    def test_whole_tool_unknown_retry_binds_actual_explicit_completion(self):
        import uuid
        import requests

        for path in ("explore", "final"):
            with self.subTest(path=path):
                prefix = [SOLVED, POLISH] if path == "explore" else [
                    NEED_PLAN, PLAN, STEP, CONTINUE, {"final_response": "1+1=2"}]
                self.open_bounded([*prefix, self.request(2, "whole_solution_verifier"),
                                   requests.Timeout("unknown verdict"), ACCEPT], 1)
                job_id = self.create_job()
                initial = self.terminal(job_id)
                unknown = initial["result"]["solver"]["recovery"]["unknown_calls"]
                self.assertEqual(1, len(unknown))
                before = len(self.outbound)
                new_id = str(uuid.uuid4())
                response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={
                    "retry_call": {"call_id": unknown[0]["call_id"], "new_call_id": new_id}},
                    headers=self.headers())
                self.assertEqual(202, response.status_code, response.get_json())
                job = self.terminal(job_id)
                self.assertEqual("succeeded", job["status"], job)
                self.assertEqual(before + 1, len(self.outbound))
                self.assertEqual(new_id, self.outbound[-1]["call_id"])
                self.assertEqual(new_id, self.report(job_id)["checks"]["source"]["call_id"])
                self.assertEqual(2, self.outbound[-1]["report"]["tool_receipts"][-1]["output"])
                self.assertEqual([{"coefficients": [2]}], self.executed)
                self.assertEqual(initial["result"]["budget"]["deadline_at"],
                                 job["result"]["budget"]["deadline_at"])
                self.doCleanups()

    def test_repeated_answered_request_never_executes_twice(self):
        self.open_bounded([NEED_PLAN, PLAN, STEP, PREMATURE, PREMATURE], 1)
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertNotEqual("succeeded", job["status"])
        self.assertEqual([{"coefficients": [1]}], self.executed)
        self.assertEqual(5, self.post.call_count)
        reviews = [item for item in self.outbound if item["role"] == "step_verifier"]
        self.assertEqual(2, len(reviews))
        receipt = reviews[-1]["report"]["tool_receipts"][0]
        self.assertEqual("success", receipt["status"])
        self.assertEqual(2, receipt["output"])
        self.assertEqual(1, self.report(job_id)["budget"]["tool_calls"])

    def test_explicit_unknown_retry_preserves_scope_count_and_deadline(self):
        import uuid
        import requests

        self.open_bounded([NEED_PLAN, PLAN, STEP, PREMATURE,
                           requests.Timeout("unknown continuation"),
                           self.request(2, "step_verifier")], 1)
        job_id = self.create_job()
        initial = self.terminal(job_id)
        unknown = initial["result"]["solver"]["recovery"]["unknown_calls"]
        self.assertEqual(1, len(unknown))
        self.assertEqual(5, self.post.call_count)  # no automatic resend
        self.assertEqual([{"coefficients": [1]}], self.executed)
        response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={"retry_call": {
            "call_id": unknown[0]["call_id"], "new_call_id": str(uuid.uuid4())}},
            headers=self.headers())
        self.assertEqual(202, response.status_code, response.get_json())
        final = self.terminal(job_id)
        self.assertNotEqual("succeeded", final["status"])
        self.assertEqual(6, self.post.call_count)
        self.assertEqual([{"coefficients": [1]}], self.executed)
        self.assertEqual(initial["result"]["budget"]["deadline_at"],
                         final["result"]["budget"]["deadline_at"])
        self.assertEqual(1, final["result"]["budget"]["unknown_attempts"])
        self.assertEqual(1, self.report(job_id)["budget"]["tool_calls"])
        receipt = self.outbound[-1]["report"]["tool_receipts"][0]
        self.assertEqual(2, receipt["output"])
        self.assertEqual("success", receipt["status"])

    def test_sixteen_exceeds_default_but_remains_bounded_by_s3(self):
        self.open_bounded([NEED_PLAN, PLAN, STEP,
                           self.request(1, "step_verifier"),
                           self.request(2, "step_verifier"),
                           self.request(3, "step_verifier"), CONTINUE,
                           {"final_response": "1+1=2"}, ACCEPT], 16, tool_limit=3)
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual("1+1=2", job["result"]["final_response"])
        self.assertEqual([{"coefficients": [1]}, {"coefficients": [2]},
                          {"coefficients": [3]}], self.executed)
        self.assertEqual(9, self.post.call_count)
        self.assertEqual(3, self.report(job_id)["budget"]["tool_calls"])
        self.assertEqual("accepted", self.report(job_id)["semantics"]["whole_review"])
        self.assertEqual("same_artifact", self.report(job_id)["semantics"]["binding"])
        step_review = next(item for item in reversed(self.outbound)
                           if item.get("role") == "step_verifier")
        receipts = step_review["report"]["tool_receipts"]
        self.assertEqual(2, receipts[-1]["output"])
        self.assertEqual(3, len(self.client.get(
            f"/api/runs/{job_id}/evidence").get_json()["tools"]))

    def test_sixteen_cannot_dispatch_after_original_deadline(self):
        import time

        def delayed_request(_context):
            time.sleep(1.1)
            return self.request(1, "explore")

        self.open_bounded([delayed_request], 16)
        pipeline = self.app.extensions["showcase_workspace_service"].star_pipeline
        pipeline.budget = RunBudgetLimits(max_model_calls=24, max_http_attempts=24,
                                         max_tool_calls=8, max_runtime_seconds=1)
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("failed", job["status"], job)
        self.assertEqual([], self.executed)
        self.assertEqual(1, self.post.call_count)
        self.assertEqual(0, self.report(job_id)["budget"]["tool_calls"])

    def test_sixteen_is_still_limited_by_shared_s3(self):
        self.open_bounded([NEED_PLAN, PLAN, STEP, PREMATURE, CONTINUE,
                           {"final_response": "1+1=2"}, ACCEPT], 16, tool_limit=1)
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual("1+1=2", job["result"]["final_response"])
        self.assertEqual([{"coefficients": [1]}], self.executed)
        self.assertEqual(7, self.post.call_count)
        self.assertEqual(1, self.report(job_id)["budget"]["tool_calls"])
        self.assertEqual("accepted", self.report(job_id)["semantics"]["whole_review"])
        self.assertEqual("same_artifact", self.report(job_id)["semantics"]["binding"])
        tools = self.client.get(f"/api/runs/{job_id}/evidence").get_json()["tools"]
        self.assertEqual(1, len(tools))


if __name__ == "__main__":
    unittest.main()
