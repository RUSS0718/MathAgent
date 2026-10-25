"""RB-02: real managed computation is distinct from comparison and review."""

import os
import time
import unittest
from copy import deepcopy

from showcase.flask_app import create_app
from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import StarJobFixture
from tests.test_star_product_python import NEED_PLAN, VERDICT

IMAGE = os.environ.get("MATHAGENT_TEST_PYTHON_IMAGE")
FEATURES = {"final_generation": True, "final_solution_review": True,
            "local_code_tool": True, "meta_guidance": True}
PLAN = {"version": 1, "steps": [{"step_id": "multiply", "title": "Multiply",
                                "objective": "Compute 17*23"}]}
FINAL = {"final_response": "17*23=17*20+17*3=340+51=391."}
ACCEPT = {"verdict": "ACCEPT", "reason": "The multiplication and explanation agree."}


@unittest.skipUnless(IMAGE, "requires a validated exact local Docker image")
class ComputationJobTest(StarJobFixture, unittest.TestCase):
    def run_computation(self, code, *, expected=(), review=VERDICT, recovery=False):
        """Use the real managed Registry; replace only provider HTTP replies."""
        step = {"argument": "17*23=391", "blocked": False, "claims": [{
            "statement": "17*23=391", "label": "easy-verify", "tool_request": {
                "tool": "python_math", "arguments": {"code": code},
                "scope": "finite_computation"}}]}
        if expected:
            step["claims"][0]["tool_request"]["expected_output"] = expected[0]
        replies = [NEED_PLAN, PLAN, step]
        if recovery:
            replies.extend([{
                "action_type": "retry_different_method", "specific_task": "Compute directly",
                "use_pure_reasoning": True, "trace_back_to": None, "rationale": "Repair"},
                {"argument": "17*20+17*3=391", "blocked": False, "claims": []}])
        replies.extend([review, FINAL, ACCEPT])
        self.open_star(replies,
            SHOWCASE_STAR_PYTHON_IMAGE_ID=IMAGE, SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                max_model_calls=10, max_http_attempts=10, max_tool_calls=2))
        response = self.client.post("/api/agent/jobs", json={"message": "计算17*23并简要解释",
            "session_id": self.session, "solver_mode": "star_limited"}, headers=self.headers())
        self.assertEqual(202, response.status_code, response.get_json())
        job_id = response.get_json()["job_id"]
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            job = self.job(job_id)
            if (not recovery and any(r["role"] == "meta" for r in self.outbound)) or job["status"] in {
                "succeeded", "failed", "canceled"}:
                break
            time.sleep(.05)
        return job_id, job

    def test_output_without_expected_continues_review_without_meta(self):
        job_id, job = self.run_computation("print(17*23)")
        self.assertNotIn("meta", [request["role"] for request in self.outbound])
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual(6, len(self.outbound))
        self.assertEqual(6, self.post.call_count)
        review = next(r for r in self.outbound if r["role"] == "step_verifier")
        receipt = review["report"]["tool_receipts"][0]
        self.assertEqual("docker_isolated", receipt["source"])
        self.assertTrue(receipt["executed"])
        self.assertTrue(receipt["cleanup_verified"])
        self.assertEqual("success", receipt["status"])
        self.assertEqual("391\n", receipt["output"])
        self.assertFalse(receipt["assertion_matched"])
        self.assertEqual("not_compared", receipt["comparison_status"])
        self.assertTrue(receipt["output_available"])
        self.assertEqual("easy-verify", review["report"]["claims"][0]["label"])
        public = job["result"]["tool_results"][0]["receipt"]
        self.assertEqual("not_compared", public["comparison_status"])
        self.assertEqual(1, self.report(job_id)["budget"]["tool_calls"])
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        self.assertIn(receipt["receipt_id"], [t.get("tool_call_id") for t in evidence["tools"]])
        stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        self.assertNotIn("meta_guidance_decided", stream)
        self.assertIn("step_reviewed", stream)
        # Reopen the persisted public Job read-only: no model/tool dispatch or rewrite.
        reopened = create_app({"TESTING": True, "SHOWCASE_DATA_DIR": self.data_dir,
            "SHOWCASE_STAR_ENABLED": True, "SHOWCASE_STAR_PYTHON_IMAGE_ID": IMAGE,
            "SHOWCASE_STAR_FEATURES": FEATURES, "SHOWCASE_WORKER_ENABLED": False})
        try:
            client = reopened.test_client()
            client.set_cookie("auth_session", self.client.get_cookie("auth_session").value)
            saved = client.get(f"/api/agent/jobs/{job_id}").get_json()
            self.assertEqual(job["result"]["tool_results"], saved["result"]["tool_results"])
            ref = public["stdout_ref"]
            stdout = client.get(f"/api/agent/jobs/{job_id}/artifacts/{ref['sha256']}")
            self.assertEqual(b"391\n", stdout.data)
            self.assertEqual(6, self.post.call_count)
        finally:
            for name in ("showcase_workspace_service", "showcase_run_service", "loopback_store"):
                reopened.extensions[name].close()

    def test_explicit_match_still_promotes_only_finite_claim(self):
        _, job = self.run_computation("print(17*23)", expected=("391\n",))
        self.assertEqual("succeeded", job["status"], job)
        review = next(r for r in self.outbound if r["role"] == "step_verifier")
        receipt = review["report"]["tool_receipts"][0]
        self.assertTrue(receipt["assertion_matched"])
        self.assertEqual("matched", receipt["comparison_status"])
        claim = review["report"]["claims"][0]
        self.assertEqual("verified", claim["label"])
        self.assertEqual("finite_computation", claim["verification_scope"])
        self.assertNotIn("meta", [r["role"] for r in self.outbound])

    def test_true_mismatch_still_triggers_bounded_guidance(self):
        _, job = self.run_computation("print(17*23)", expected=("392\n",), recovery=True)
        self.assertEqual("succeeded", job["status"], job)
        metas = [r for r in self.outbound if r["role"] == "meta"]
        self.assertEqual(1, len(metas))
        self.assertEqual("code_issue", metas[0]["guidance_request"]["failure_type"])
        self.assertEqual("output_mismatch", metas[0]["tool_failure"])
        receipt = job["result"]["tool_results"][0]["receipt"]
        self.assertEqual("mismatched", receipt["comparison_status"])
        self.assertFalse(receipt["assertion_matched"])
        self.assertEqual(8, self.post.call_count)

    def test_execution_error_still_triggers_guidance_without_comparison(self):
        _, job = self.run_computation("raise ValueError('bad calculation')", recovery=True)
        self.assertEqual("succeeded", job["status"], job)
        meta = next(r for r in self.outbound if r["role"] == "meta")
        self.assertEqual("execution_error", meta["tool_failure"])
        receipt = job["result"]["tool_results"][0]["receipt"]
        self.assertEqual("tool_error", receipt["status"])
        self.assertEqual("not_compared", receipt["comparison_status"])
        self.assertFalse(receipt["output_available"])

    def test_stdout_from_failed_execution_is_available_but_not_compared(self):
        _, job = self.run_computation("print(391); raise ValueError('incomplete')",
                                      expected=("391\n",), recovery=True)
        self.assertEqual("succeeded", job["status"], job)
        receipt = job["result"]["tool_results"][0]["receipt"]
        self.assertEqual("tool_error", receipt["status"])
        self.assertTrue(receipt["output_available"])
        self.assertFalse(receipt["assertion_matched"])
        self.assertEqual("not_compared", receipt["comparison_status"])

    def test_expression_without_stdout_cannot_back_computation_outcome(self):
        def classify(context):
            receipt = context["report"]["tool_receipts"][0]
            return {**deepcopy(VERDICT), "classified_outcomes": [{
                "category": "Computation", "statement": "17*23=391",
                "scope": "finite calculation", "claim_indexes": [0],
                "receipt_ids": [receipt["receipt_id"]]}]}

        job_id, job = self.run_computation("17*23", expected=("",), review=classify)
        self.assertNotIn("meta", [r["role"] for r in self.outbound])
        self.assertEqual("succeeded", job["status"], job)
        receipt = job["result"]["tool_results"][0]["receipt"]
        self.assertFalse(receipt["output_available"])
        self.assertFalse(receipt["assertion_matched"])
        self.assertEqual("not_compared", receipt["comparison_status"])
        entries = self.report(job_id)["solver"]["solver"]["progress"]["classified_results"]
        self.assertEqual([], entries)
