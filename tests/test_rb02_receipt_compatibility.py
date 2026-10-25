"""Supplement public Docker acceptance with structured-output and legacy reads."""

import unittest
from copy import deepcopy

from showcase.run_budget import RunBudgetLimits
from showcase.solver_harness import (
    ScriptedMetaPort,
    ScriptedModelPort,
    ScriptedToolPort,
    ScriptedVerifierPort,
    SolverHarness,
    replay_snapshot,
)
from showcase.solver_harness.computation_evidence import has_computation_output
from showcase.solver_harness.verification import verify_step
from showcase.tools import ToolRegistry
from tests.star_product_support import StarJobFixture
from tests.test_star_product_tools import ACCEPT, FEATURES, NEED_PLAN, PLAN, STEP, VERDICT


class StructuredOutputJobTest(StarJobFixture, unittest.TestCase):
    def test_falsey_structured_results_are_available_and_comparable(self):
        for value in (0, False, [], {}):
            with self.subTest(value=value):
                registry = ToolRegistry()
                registry.register("polynomial_check", lambda args: value)
                step = deepcopy(STEP)
                step["claims"][0]["tool_request"]["expected_output"] = value
                self.open_star([NEED_PLAN, PLAN, step, VERDICT, {"final_response": "2"}, ACCEPT],
                    SHOWCASE_STAR_FEATURES=FEATURES, SHOWCASE_STAR_REGISTRY=registry,
                    SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                        max_model_calls=8, max_http_attempts=8, max_tool_calls=2))
                job = self.terminal(self.create_job())
                self.assertEqual("succeeded", job["status"], job)
                review = next(r for r in self.outbound if r["role"] == "step_verifier")
                receipt = review["report"]["tool_receipts"][0]
                self.assertTrue(receipt["output_available"])
                self.assertTrue(receipt["assertion_matched"])
                self.assertEqual("matched", receipt["comparison_status"])
                self.assertEqual(type(value), type(receipt["output"]))
                self.assertEqual(value, receipt["output"])


class LegacyReceiptTest(unittest.TestCase):
    def test_legacy_output_reads_require_observable_result_without_mutation(self):
        for receipt, available in [
            ({"assertion_matched": True, "stdout_ref": "old:stdout"}, False),
            ({"tool": "python_math", "output": " \n", "assertion_matched": True}, False),
            ({"tool": "python_math", "output": "0\n", "assertion_matched": False}, True),
            ({"output": 0}, True), ({"output": False}, True),
            ({"output": []}, True), ({"output": {}}, True), ({"output": None}, False),
        ]:
            with self.subTest(receipt=receipt):
                saved = deepcopy(receipt)
                self.assertEqual(available, has_computation_output(receipt))
                self.assertEqual(saved, receipt)

    def test_legacy_boolean_does_not_invent_mismatch_or_reexecute_during_review(self):
        class Paused(BaseException):
            """Simulate interruption at a committed report boundary."""

        def pause(run, event):
            if event["type"] == "step_reported":
                raise Paused()

        for matched in (False, True):
            with self.subTest(legacy_boolean=matched):
                verifier = ScriptedVerifierPort([VERDICT])
                meta = ScriptedMetaPort([])
                tool = ScriptedToolPort([])
                with SolverHarness(config={"features": {"meta_guidance": True},
                        "max_model_calls": 8},
                        model_port=ScriptedModelPort([STEP]), verifier_port=verifier,
                        meta_port=meta, tool_port=tool, event_observer=pause) as harness:
                    with self.assertRaises(Paused):
                        harness.solve("1+1", {"run_id": "legacy", "plan": PLAN})
                    run = harness.get_run("legacy")
                    step_id = run["state"]["current_step"]
                    receipt = {"receipt_id": "legacy:receipt", "step_id": step_id,
                        "claim_index": 0, "tool": "python_math", "source": "docker_isolated",
                        "executed": True, "status": "success", "exit_code": 0,
                        "cleanup_verified": True, "assertion_matched": matched,
                        "output": "2\n", "stdout_ref": "legacy:stdout"}
                    steps = deepcopy(run["state"]["steps"])
                    report = steps[step_id]["report"]
                    report.update(prechecked=True, tool_receipts=[receipt],
                                  tool_evidence_refs=[receipt["receipt_id"]])
                    report["claims"][0].pop("tool_request", None)
                    report["claims"][0]["tool_evidence_refs"] = [receipt["receipt_id"]]
                    harness.commit_event("legacy", expected_revision=run["state_revision"],
                        event={"type": "tool_receipt", "event_id": "legacy:receipt", "receipt": receipt},
                        state_updates={"steps": steps, "tool_receipts": [receipt]})
                    result = verify_step(harness, harness.get_run("legacy"), problem="1+1",
                        verifier_port=verifier, max_model_calls=8, max_runtime_seconds=60)
                    self.assertEqual([], meta.requests)
                    self.assertEqual([], tool.requests)
                    self.assertEqual(1, len(verifier.requests))
                    self.assertEqual(receipt, result["state"]["tool_receipts"][0])
                    self.assertEqual("easy-verify", verifier.requests[0]["report"]["claims"][0]["label"])
                    saved = deepcopy(result)
                    replay_snapshot(result)
                    self.assertEqual(saved, result)
