"""Tool ceilings constrain execution without truncating a public STAR answer."""

import os
import unittest
from copy import deepcopy

from showcase.run_budget import RunBudgetLimits
from showcase.tools import ToolRegistry
from tests.star_product_support import ACCEPT, POLISH, SOLVED, StarJobFixture
from tests.test_star_product_explore_compute import CONTINUE, ENUMERATE


class StarToolCeilingTest(StarJobFixture, unittest.TestCase):
    def open_with_ceiling(self, replies, *, tool_calls, model_calls=6):
        """Use the public Job fixture with a counted, real Registry handler."""
        self.executed = []
        registry = ToolRegistry()
        registry.register("polynomial_check", lambda args: self.executed.append(args) or 2)
        self.open_star(
            replies,
            SHOWCASE_STAR_FEATURES={"local_code_tool": True},
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                max_model_calls=model_calls, max_http_attempts=8,
                max_tool_calls=tool_calls, max_tokens=32768,
            ),
            SHOWCASE_STAR_REGISTRY=registry,
        )

    def assert_complete_answer(self, job_id):
        """The delivered answer must finish review and bind to the same text."""
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual("1+1=2", job["result"]["final_response"])
        report = self.report(job_id)
        self.assertEqual("accepted", report["semantics"]["whole_review"])
        self.assertEqual("same_artifact", report["semantics"]["binding"])
        self.assertEqual(0, report["budget"]["unknown_attempts"])
        self.assertEqual(0, report["budget"]["reserved_tokens"])
        return report

    def test_last_allowed_tool_receipt_continues_through_complete_answer(self):
        deadlines = []

        def continue_with_receipt(context):
            deadlines.append(self.report(context["run_id"])["budget"]["deadline_at"])
            return CONTINUE

        self.open_with_ceiling([ENUMERATE, continue_with_receipt, POLISH, ACCEPT], tool_calls=1)
        job_id = self.create_job()
        report = self.assert_complete_answer(job_id)

        self.assertEqual([{"coefficients": [1]}], self.executed)
        self.assertEqual(1, report["budget"]["tool_calls"])
        self.assertEqual(4, report["budget"]["http_attempts"])
        self.assertEqual(40, report["budget"]["provider_known"]["total_tokens"])
        self.assertEqual([report["budget"]["deadline_at"]], deadlines)
        continuation = self.outbound[1]
        self.assertEqual("explore", continuation["role"])
        self.assertEqual([], continuation.get("allowed_tools", []))
        receipt = continuation["report"]["tool_receipts"][0]
        self.assertTrue(receipt["executed"])
        self.assertEqual("success", receipt["status"])
        self.assertEqual(2, receipt["output"])

    def test_zero_tool_ceiling_still_allows_a_reviewed_pure_reasoning_answer(self):
        self.open_with_ceiling([SOLVED, POLISH, ACCEPT], tool_calls=0)
        job_id = self.create_job()
        report = self.assert_complete_answer(job_id)

        self.assertEqual([], self.executed)
        self.assertEqual(0, report["budget"]["tool_calls"])
        self.assertEqual(3, report["budget"]["logical_calls"])
        self.assertTrue(all(not request.get("allowed_tools") for request in self.outbound))

    def test_extra_tool_is_denied_and_model_can_complete_without_it(self):
        second_request = deepcopy(ENUMERATE)
        second_request["tool_request"]["arguments"] = {"coefficients": [2]}
        self.open_with_ceiling(
            [ENUMERATE, second_request, CONTINUE, POLISH, ACCEPT], tool_calls=1,
        )
        job_id = self.create_job()
        report = self.assert_complete_answer(job_id)

        self.assertEqual([{"coefficients": [1]}], self.executed)
        self.assertEqual(1, report["budget"]["tool_calls"])
        self.assertEqual(5, report["budget"]["http_attempts"])
        receipts = self.outbound[2]["report"]["tool_receipts"]
        self.assertEqual(2, len(receipts))
        self.assertFalse(receipts[1]["executed"])
        self.assertEqual("not_executed", receipts[1]["status"])
        self.assertEqual("tool_call_budget_exhausted", receipts[1]["reason"])
        self.assertIsNone(receipts[1]["output"])

    def test_model_ceiling_still_stops_continuation_after_successful_tool(self):
        self.open_with_ceiling([ENUMERATE], tool_calls=1, model_calls=1)
        job_id = self.create_job()
        job = self.terminal(job_id)

        self.assertEqual("failed", job["status"], job)
        self.assertEqual([{"coefficients": [1]}], self.executed)
        self.assertEqual(1, len(self.outbound))
        self.assertEqual(1, self.report(job_id)["budget"]["http_attempts"])
        self.assertEqual("not_reviewed", self.report(job_id)["semantics"]["whole_review"])


@unittest.skipUnless(os.environ.get("MATHAGENT_TEST_PYTHON_IMAGE"),
                     "requires independently validated local Docker image ID")
class StarReferenceToolCeilingTest(StarJobFixture, unittest.TestCase):
    def test_reference_finishes_after_last_isolated_tool_call(self):
        """The full public Reference path can review its final allowed computation."""
        image = os.environ["MATHAGENT_TEST_PYTHON_IMAGE"]
        probe = {**ENUMERATE, "tool_request": {
            "tool": "python_math", "arguments": {"code": "print(1 + 1)"},
            "scope": "finite_computation", "expected_output": "2\n",
        }}
        self.open_star(
            [probe, CONTINUE, POLISH, ACCEPT],
            SHOWCASE_STAR_FULL_ENABLED=True, SHOWCASE_STAR_PYTHON_IMAGE_ID=image,
            SHOWCASE_STAR_FULL_BUDGET=RunBudgetLimits(
                max_model_calls=6, max_http_attempts=8, max_tool_calls=1,
            ),
        )
        response = self.client.post("/api/agent/jobs", json={
            "message": "Compute 1+1.", "session_id": self.session,
            "solver_mode": "star_reference",
        }, headers=self.headers())
        self.assertEqual(202, response.status_code, response.get_json())
        job_id = response.get_json()["job_id"]
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual("1+1=2", job["result"]["final_response"])
        self.assertEqual("star_reference", job["result"]["execution_mode"])
        self.assertEqual([], job["result"]["missing_capabilities"])
        report = self.report(job_id)
        self.assertEqual(1, report["budget"]["tool_calls"])
        self.assertEqual(4, report["budget"]["http_attempts"])
        self.assertEqual("accepted", report["semantics"]["whole_review"])
        self.assertEqual("same_artifact", report["semantics"]["binding"])
        continuation = self.outbound[1]
        self.assertEqual([], continuation["allowed_tools"])
        receipt = continuation["report"]["tool_receipts"][0]
        self.assertTrue(receipt["executed"])
        self.assertTrue(receipt["cleanup_verified"])
        self.assertEqual("2\n", receipt["output"])
        self.assertEqual(image, receipt["image"])


if __name__ == "__main__":
    unittest.main()
