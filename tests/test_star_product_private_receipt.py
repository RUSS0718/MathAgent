"""Public tool receipts must not reveal private planner step IDs."""

import json
import unittest
from copy import deepcopy
from unittest.mock import patch

from showcase.run_budget import RunBudgetLimits
from showcase.tools import ToolRegistry
from tests.star_product_support import ACCEPT, StarJobFixture

PRIVATE_STEP_ID = "PRIVATE_HINT_REF_39471"
PRIVATE_TOOL_NAME = "PRIVATE_TOOL_HINT_6822"
NEED_PLAN = {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []}
PLAN = {"version": 1, "steps": [{"step_id": PRIVATE_STEP_ID,
    "title": "Factor", "objective": "Factor x^2 - 1"}]}
STEP = {"argument": "Factor the difference of squares", "blocked": False, "claims": [{
    "statement": "x^2 - 1 = (x - 1)(x + 1)", "label": "easy-verify", "tool_request": {
        "tool": "polynomial_check", "arguments": {
            "schema_version": 1, "variable": "x", "coefficients": ["1", "0", "-1"],
            "domain": {"kind": "real"}, "candidates": ["-1", "1"]},
        "scope": "finite_computation"}}]}
VERDICT = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": ""}
FINAL = {"final_response": "x^2 - 1 = (x - 1)(x + 1)."}
FEATURES = {"final_generation": True, "final_solution_review": True, "local_code_tool": True}


class PrivateToolReceiptTest(StarJobFixture, unittest.TestCase):
    def test_private_planner_step_id_is_ordinalized_in_public_tool_receipts(self):
        registry = ToolRegistry()
        registry.register_polynomial_check()
        self.open_star([NEED_PLAN, PLAN, STEP, VERDICT, FINAL, ACCEPT],
            SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8, max_tool_calls=2),
            SHOWCASE_STAR_REGISTRY=registry)
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        tool_results = job["result"]["tool_results"]
        self.assertEqual(1, len(tool_results))
        self.assertEqual("步骤 1", tool_results[0]["receipt"]["step_id"])

        run = self.client.get(f"/api/runs/{job_id}").get_json()
        report = self.client.get(f"/api/agent/jobs/{job_id}/report").get_json()
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        events = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)

        def receipts(value):
            if isinstance(value, dict):
                if isinstance(value.get("receipt"), dict):
                    yield value["receipt"]
                for child in value.values():
                    yield from receipts(child)
            elif isinstance(value, list):
                for child in value:
                    yield from receipts(child)

        # Request-attempt call IDs are projected by SP-04; this checks receipt step IDs only.
        job_receipts = list(receipts(job))
        run_receipts = list(receipts(run))
        self.assertEqual(1, len(job_receipts))
        self.assertEqual(1, len(run_receipts))
        for surface_receipts in (job_receipts, run_receipts, list(receipts(report)),
                list(receipts(evidence)), list(receipts(events))):
            for receipt in surface_receipts:
                self.assertEqual("步骤 1", receipt["step_id"])
                self.assertNotIn(PRIVATE_STEP_ID, json.dumps(receipt, ensure_ascii=False))
        self.assertNotIn(PRIVATE_STEP_ID, json.dumps(report["report"].get("tool_summaries", []), ensure_ascii=False))
        self.assertNotIn(PRIVATE_STEP_ID, json.dumps(evidence.get("tools", []), ensure_ascii=False))

        reasoner = next(item for item in self.outbound if item["role"] == "reasoner")
        self.assertEqual(PRIVATE_STEP_ID, reasoner["step"]["step_id"])

    def test_private_unsupported_tool_name_is_not_projected(self):
        from showcase.solver_harness.intern_port import schema_error as validate_schema

        response = deepcopy(STEP)
        response["claims"][0]["tool_request"]["tool"] = PRIVATE_TOOL_NAME

        def allow_injected_name(value, schema):
            validated = deepcopy(value)
            if isinstance(validated, dict):
                for claim in validated.get("claims", []):
                    request = claim.get("tool_request") if isinstance(claim, dict) else None
                    if isinstance(request, dict) and request.get("tool") == PRIVATE_TOOL_NAME:
                        request["tool"] = "polynomial_check"
            return validate_schema(validated, schema)

        registry = ToolRegistry()
        registry.register_polynomial_check()
        with patch("showcase.solver_harness.intern_port.schema_error", side_effect=allow_injected_name):
            self.open_star([NEED_PLAN, PLAN, response, VERDICT, FINAL, ACCEPT],
                SHOWCASE_STAR_FEATURES=FEATURES,
                SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8, max_tool_calls=2),
                SHOWCASE_STAR_REGISTRY=registry)
            job_id = self.create_job()
            job = self.terminal(job_id)
            self.assertEqual("succeeded", job["status"], job)
            self.assertEqual(0, self.report(job_id)["budget"]["tool_calls"])
            result = job["result"]["tool_results"][0]
            self.assertEqual("unsupported", result["name"])
            self.assertEqual("unsupported", result["receipt"]["tool"])

            run = self.client.get(f"/api/runs/{job_id}").get_json()
            report = self.client.get(f"/api/agent/jobs/{job_id}/report").get_json()
            evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
            events = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
            for surface in (job, run, report, evidence, events):
                serialized = surface if isinstance(surface, str) else json.dumps(surface, ensure_ascii=False)
                self.assertNotIn(PRIVATE_TOOL_NAME, serialized)


if __name__ == "__main__":
    unittest.main()
