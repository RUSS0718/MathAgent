"""Explore routing contracts through the public Solver Harness seam."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from showcase.solver_harness import ScriptedModelPort, SolverHarness


class SolverHarnessExploreTest(unittest.TestCase):
    def test_solved_without_verifier_is_explicitly_unverified(self) -> None:
        port = ScriptedModelPort([{"assessment": "SOLVED", "solution_candidate": "42"}])
        with SolverHarness(model_port=port) as harness:
            result = harness.solve("计算答案", {"run_id": "solved"})
            self.assertEqual("TERMINAL", result["state"]["phase"])
            self.assertEqual("completed_unverified", result["state"]["status"])
            self.assertTrue(result["state"]["final_response"])
            self.assertEqual([], result["state"]["accepted_results"])
            self.assertEqual(1, len(port.requests))

    def test_exhausted_budget_returns_explicit_result_without_dispatch(self) -> None:
        for config, reason in [
            ({"max_model_calls": 0}, "model_call_budget_exhausted"),
            ({"max_total_duration_seconds": 0}, "runtime_budget_exhausted"),
        ]:
            with self.subTest(config=config):
                port = ScriptedModelPort([{"assessment": "SOLVED"}])
                with SolverHarness(model_port=port, config=config) as harness:
                    result = harness.solve("计算答案", {"run_id": "exhausted"})
                    self.assertEqual(result, harness.get_run("exhausted"))
                self.assertEqual([], port.requests)
                self.assertEqual(0, result["state"]["counters"]["model_calls"])
                self.assertEqual(reason, result["state"]["budget"]["exhaustion_reason"])
                self.assertTrue(result["state"]["final_response"])
                self.assertEqual([], result["state"]["accepted_results"])
                json.dumps(result, allow_nan=False)

    def test_need_plan_routes_directly_to_plan_without_meta(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            port = ScriptedModelPort([{"assessment": "NEED_PLAN"}])
            database_path = Path(directory) / "showcase.sqlite3"
            with SolverHarness(
                database_path=database_path,
                model_port=port,
                config={"max_model_calls": 2, "max_explore_rounds": 2},
            ) as harness:
                harness.solve("证明一个命题", {"run_id": "solver-need-plan"})
                recovered = harness.get_run("solver-need-plan", problem="证明一个命题")

            self.assertEqual("PLAN", recovered["state"]["phase"])
            self.assertEqual(1, recovered["state"]["counters"]["model_calls"])
            self.assertEqual(["explore"], [request["role"] for request in port.requests])
            self.assertEqual(
                "NEED_PLAN", recovered["state"]["exploration_findings"][0]["assessment"]
            )
            json.dumps(recovered)

    def test_partial_retry_checks_remaining_budget_before_dispatch(self) -> None:
        port = ScriptedModelPort([{"assessment": "PARTIALLY_SOLVED"}])
        with SolverHarness(model_port=port, config={"max_model_calls": 1}) as harness:
            result = harness.solve("计算答案", {"run_id": "partial-budget"})
        self.assertEqual(1, len(port.requests))
        self.assertEqual(1, result["state"]["counters"]["model_calls"])
        self.assertEqual("partial_budget_exhausted", result["state"]["status"])
        self.assertTrue(result["state"]["final_response"])

    def test_malformed_assessment_becomes_unknown_and_routes_to_plan(self) -> None:
        port = ScriptedModelPort([{"assessment": ["SOLVED"]}])
        with SolverHarness(model_port=port) as harness:
            result = harness.solve("计算答案", {"run_id": "invalid"})
        self.assertEqual("PLAN", result["state"]["phase"])
        self.assertEqual("UNKNOWN", result["state"]["exploration_findings"][0]["assessment"])

    def test_unknown_routes_directly_to_plan_without_meta(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            port = ScriptedModelPort([{"assessment": "UNKNOWN"}])
            database_path = Path(directory) / "showcase.sqlite3"
            with SolverHarness(database_path=database_path, model_port=port) as harness:
                harness.solve("证明一个命题", {"run_id": "solver-unknown"})
                recovered = harness.get_run("solver-unknown")

            self.assertEqual("PLAN", recovered["state"]["phase"])
            self.assertEqual("UNKNOWN", recovered["state"]["exploration_findings"][0]["assessment"])
            self.assertEqual(["explore"], [request["role"] for request in port.requests])
            self.assertEqual(1, recovered["state"]["counters"]["model_calls"])

    def test_partial_exploration_gets_one_retry_then_routes_to_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            port = ScriptedModelPort(
                [
                    {"assessment": "PARTIALLY_SOLVED", "worked": ["已找到一个模式"]},
                    {"assessment": "PARTIALLY_SOLVED", "failed": ["边界仍未覆盖"]},
                ]
            )
            database_path = Path(directory) / "showcase.sqlite3"
            with SolverHarness(
                database_path=database_path, model_port=port, config={"max_explore_rounds": 50}
            ) as harness:
                harness.solve("证明一个命题", {"run_id": "solver-partial-retry"})
                recovered = harness.get_run("solver-partial-retry")

            self.assertEqual("PLAN", recovered["state"]["phase"])
            self.assertEqual(2, recovered["state"]["counters"]["model_calls"])
            self.assertEqual(2, len(recovered["state"]["exploration_findings"]))
            self.assertEqual([1, 2], [request["round"] for request in port.requests])
            self.assertEqual(["explore", "explore"], [request["role"] for request in port.requests])


if __name__ == "__main__":
    unittest.main()
