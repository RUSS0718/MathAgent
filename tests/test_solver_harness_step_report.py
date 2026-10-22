"""Step reports through the public Solver Harness entry and recovery seam."""

import tempfile
import unittest
from pathlib import Path

from showcase.solver_harness import ScriptedModelPort, SolverHarness


class SolverHarnessStepReportTest(unittest.TestCase):
    def test_supplied_plan_persists_conservative_step_report_for_review(self) -> None:
        plan = {"version": 1, "steps": [{"step_id": "s1", "objective": "计算平方"}]}
        port = ScriptedModelPort(
            [
                {
                    "argument": "计算得到 4",
                    "claims": [
                        {
                            "statement": "2² = 4",
                            "label": "verified",
                            "tool_evidence_refs": ["fake"],
                        },
                        {"statement": "可重新计算", "label": "easy-verify"},
                        {"statement": "需要证明", "label": ["verified", "hard-verify"]},
                    ],
                    "tool_evidence_refs": ["fake"],
                    "blocked": False,
                }
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "solver.sqlite3"
            with SolverHarness(database_path=path, model_port=port) as harness:
                result = harness.solve("计算 2²", {"run_id": "step", "plan": plan})
                self.assertEqual("STEP_VERIFY", result["state"]["phase"])
                self.assertEqual("VERIFYING", result["state"]["steps"]["s1"]["status"])
                report = result["state"]["steps"]["s1"]["report"]
                self.assertEqual("s1", report["step_id"])
                self.assertEqual("计算平方", report["objective"])
                self.assertEqual("计算得到 4", report["argument"])
                self.assertFalse(report["blocked"])
                self.assertEqual([], report["tool_evidence_refs"])
                self.assertEqual(
                    ["hard-verify", "easy-verify", "hard-verify"],
                    [claim["label"] for claim in report["claims"]],
                )
                self.assertEqual([], report["claims"][0]["tool_evidence_refs"])
                self.assertEqual([], result["state"]["tool_policy"]["allow"])
                self.assertEqual(0, result["state"]["counters"]["tool_calls"])
            with SolverHarness(database_path=path) as recovered:
                self.assertEqual(result, recovered.get_run("step"))
        self.assertEqual(["reasoner"], [request["role"] for request in port.requests])
        self.assertEqual("s1", port.requests[0]["step"]["step_id"])

    def test_recovering_report_does_not_dispatch_another_step(self) -> None:
        plan = {"version": 1, "steps": [{"step_id": "s1", "objective": "求值"}]}
        port = ScriptedModelPort(
            [
                {
                    "claims": [{"statement": "待验证", "label": "verified"}],
                    "blocked": True,
                }
            ]
        )
        with SolverHarness(model_port=port) as harness:
            metadata = {"run_id": "repeat", "plan": plan}
            result = harness.solve("计算", metadata)
            self.assertEqual(result, harness.solve("计算", metadata))
        self.assertEqual(1, len(port.requests))
        report = result["state"]["steps"]["s1"]["report"]
        self.assertTrue(report["blocked"])
        self.assertEqual("hard-verify", report["claims"][0]["label"])

    def test_supplied_plan_respects_budget_before_dispatch(self) -> None:
        plan = {"version": 1, "steps": [{"step_id": "s1", "objective": "求值"}]}
        for config in ({"max_model_calls": 0}, {"max_total_duration_seconds": 0}):
            with self.subTest(config=config):
                port = ScriptedModelPort([])
                with SolverHarness(model_port=port, config=config) as harness:
                    result = harness.solve("计算", {"plan": plan})
                self.assertEqual([], port.requests)
                self.assertEqual("partial_budget_exhausted", result["state"]["status"])
                self.assertEqual({}, result["state"]["steps"])


if __name__ == "__main__":
    unittest.main()
