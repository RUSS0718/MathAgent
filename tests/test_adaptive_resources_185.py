"""Shared admission preserves adaptive reserves without changing root identity."""

import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from showcase.run_budget import BudgetExhausted, RunBudgetLedger, RunBudgetLimits, bind_budget
from showcase.solver_harness.adaptive_resources import allocate, bind_allocation


class AdaptiveResourceTest(unittest.TestCase):
    def setUp(self):
        self.ledger = RunBudgetLedger()
        self.addCleanup(self.ledger.close)
        self.budget = self.ledger.ensure("r", RunBudgetLimits(
            max_model_calls=8, max_http_attempts=8, max_tokens=100_000,
            max_runtime_seconds=7200))
        self.harness = SimpleNamespace(
            _config={"features": {}},
            prepare_request=lambda run, request, **kwargs: request,
            _model_port=SimpleNamespace(
                adapter=SimpleNamespace(max_tokens=256, client_timeout=360,
                                        _get_client=lambda: SimpleNamespace(timeout=360, retry=0))))
        self.run = {"run_id": "r", "state": {
            "adaptive_solving": {"version": "adaptive-solving-v1"},
            "adaptive_resource_policy": "adaptive-resources-v1"}}

    def test_old_runs_do_not_acquire_the_new_resource_policy(self):
        self.run["state"].pop("adaptive_resource_policy")
        with bind_budget(self.budget):
            self.assertEqual(({}, None), allocate(self.harness, self.run, {"role": "explore"}))

    def test_transport_attempts_share_one_logical_call_time_reserve(self):
        self.harness._model_port.adapter._get_client = lambda: SimpleNamespace(timeout=360, retry=3)
        with bind_budget(self.budget):
            floor, error = allocate(self.harness, self.run, {"role": "planner", "problem": "P"})
        self.assertIsNone(error)
        self.assertEqual(1080, floor["time_seconds"])
        self.assertEqual(self.budget.snapshot()["deadline_at"] - 1080,
                         floor["work_deadline_at"])

    @patch("showcase.run_budget.time.time", return_value=2_000_000_000.0)
    def test_work_deadline_leaves_final_pair_and_repair_without_resetting_root(self, clock):
        clock.return_value = self.budget.snapshot()["started_at"]
        original = self.budget.snapshot()
        with bind_budget(self.budget):
            floor, error = allocate(self.harness, self.run, {
                "role": "reasoner", "problem": "P", "repair_instruction": None})
        self.assertIsNone(error)
        self.assertEqual(3, floor["model_calls"])
        self.assertEqual(1080, floor["time_seconds"])
        self.assertGreater(floor["work_deadline_at"] - time.time(), 6000)
        self.assertEqual(original["deadline_at"] - 1080, floor["work_deadline_at"])
        self.assertEqual(original, self.budget.snapshot())

    def test_atomic_admission_checks_actual_http_input_against_preserved_tokens(self):
        floor = {"model_calls": 2, "http_attempts": 2, "tokens": 90_000}
        with bind_allocation("r", floor):
            self.budget.model_call("reasoner")
            with self.assertRaises(BudgetExhausted):
                self.ledger.reserve("r", "http", input_estimate=10_000, output_cap=1)
        self.assertEqual(0, self.budget.snapshot()["http_attempts"])
        # Leaving the stage restores normal admission; the root was never resized.
        self.ledger.reserve("r", "http", input_estimate=10_000, output_cap=1)
        self.assertEqual(1, self.budget.snapshot()["http_attempts"])

    def test_repair_consumes_its_slot_and_uses_the_same_root_deadline(self):
        with bind_budget(self.budget):
            first, error = allocate(self.harness, self.run, {"role": "explore", "problem": "P"})
            repair, repair_error = allocate(self.harness, self.run, {
                "role": "explore", "problem": "P", "repair_instruction": "repair"})
        self.assertIsNone(error)
        self.assertIsNone(repair_error)
        self.assertEqual(2, first["model_calls"])
        self.assertEqual(1, repair["model_calls"])
        self.assertEqual(first["work_deadline_at"] + 360, repair["work_deadline_at"])

    def test_existing_finalization_and_population_reservations_are_not_counted_twice(self):
        with bind_budget(self.budget):
            self.assertEqual(({}, None), allocate(self.harness, self.run, {
                "role": "final_generator", "finalization_scope": True}))
            self.run["state"]["population_policy"] = {"enabled": True}
            self.assertEqual(({}, None), allocate(self.harness, self.run, {"role": "reasoner"}))

    def test_floor_is_scoped_to_one_run_and_reset_even_after_an_exception(self):
        with self.assertRaises(RuntimeError):
            with bind_allocation("other-run", {"model_calls": 100}):
                self.budget.model_call("reasoner")
                raise RuntimeError("leave scope")
        self.budget.model_call("reasoner")
        self.assertEqual(2, self.budget.snapshot()["logical_calls"])
