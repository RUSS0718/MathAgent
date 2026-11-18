"""Exercise admission conflicts through independent persistent store connections."""

import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace

from showcase.solver_harness.population_store import PopulationConflict, command
from showcase.solver_harness.storage import SolverStateStore
from showcase.storage import SQLiteStore
from tests import test_population_store as fixture

RUN_ID = fixture.RUN_ID


class PopulationAdmissionTests(unittest.TestCase):
    setUp = fixture.PopulationStoreTests.setUp
    tearDown = fixture.PopulationStoreTests.tearDown
    _admit = fixture.PopulationStoreTests._admit

    def test_equivalent_frontier_rejection_does_not_change_state_or_budget(self):
        before = self.state_store.get_run(RUN_ID)
        budget = self.budget.snapshot()
        with self.assertRaisesRegex(PopulationConflict, "duplicate_route_frontier"):
            command(
                self.harness,
                RUN_ID,
                "register_route",
                route_id="renamed-route",
                frontier_digest="frontier-a",
                snapshot=before["state"]["population"]["routes"]["route-a"]["snapshot"],
            )
        self.assertEqual(before, self.state_store.get_run(RUN_ID))
        after = self.budget.snapshot()
        for key in budget.keys() - {"wall_time_seconds"}:
            self.assertEqual(budget[key], after[key], key)

    def test_same_action_replay_does_not_reserve_or_emit_again(self):
        first = self._admit()
        budget = self.budget.snapshot()
        self._admit()
        self.assertEqual(first, self.state_store.get_run(RUN_ID))
        after = self.budget.snapshot()
        for key in budget.keys() - {"wall_time_seconds"}:
            self.assertEqual(budget[key], after[key], key)

    def test_independent_connections_admit_same_route_only_once(self):
        barrier = Barrier(2)
        owner = dict(self.harness._population_owner)

        def compete(action_id):
            with SQLiteStore(self.database) as store:
                harness = SimpleNamespace(
                    _state_store=SolverStateStore(store._connection),
                    _showcase_store=store,
                    _population_owner=owner,
                    _event_observer=None,
                )
                barrier.wait(timeout=5)
                try:
                    command(
                        harness,
                        RUN_ID,
                        "admit",
                        route_id="route-a",
                        action_id=action_id,
                        reservation={
                            "calls": [
                                {
                                    "role": "reasoner",
                                    "input_estimate": 20,
                                    "output_cap": 10,
                                    "http_attempts": 1,
                                }
                            ],
                            "model_calls": 1,
                            "http_attempts": 1,
                            "tokens": 30,
                            "tool_calls": 0,
                            "time_seconds": 2,
                        },
                        closing_reserve={
                            "model_calls": 1,
                            "http_attempts": 1,
                            "tokens": 20,
                            "time_seconds": 1,
                            "tool_calls": 0,
                        },
                        dependencies=[],
                    )
                    return "admitted"
                except PopulationConflict:
                    return "rejected"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(compete, ["race-a", "race-b"]))
        self.assertCountEqual(["admitted", "rejected"], outcomes)
        population = self.state_store.get_run(RUN_ID)["state"]["population"]
        self.assertEqual(1, len(population["actions"]))
        self.assertIn(population["routes"]["route-a"]["inflight_action_id"], population["actions"])
        budget = self.budget.snapshot()
        self.assertEqual(
            (1, 1, 30), (budget["logical_calls"], budget["http_attempts"], budget["charged_tokens"])
        )


if __name__ == "__main__":
    unittest.main()
