"""Round fairness is a dispatch boundary, independent of completion order."""

import unittest

from showcase.solver_harness.population_schedule import replay_rating, round_schedule


def route(status="eligible", **fields):
    return {"status": status, "produced": [], "adopted": [], **fields}


class PopulationScheduleTest(unittest.TestCase):
    def test_shared_closing_failure_yields_without_new_dispatch(self):
        from unittest.mock import Mock, patch

        from showcase.solver_harness.population_runtime import tick

        run = {"run_id": "paused", "state_revision": 3, "state": {
            "population": {"paused_reason": "population_closing_reserve_unavailable"},
            "obligation_ledger": [{"status": "open"}],
        }}
        harness = Mock()
        harness._population_futures = {}
        harness._state_store.get_run.return_value = run
        with patch("showcase.solver_harness.population_runtime._collect", return_value=run), \
             patch("showcase.solver_harness.population_runtime._refresh_closing_reserve", return_value=run), \
             patch("showcase.solver_harness.population_runtime.command", return_value=run) as command:
            tick(harness, run, "problem")
        command.assert_not_called()
        self.assertEqual("interrupted", harness.commit_event.call_args.kwargs["state_updates"]["status"])

    def test_fixed_round_admits_new_routes_only_next_round(self):
        pop = {"routes": {"a": route(), "b": route()}, "round": 0}
        first = round_schedule(pop)
        self.assertEqual(["a", "b"], first["order"])
        pop.update(first)
        pop["opportunities"] = ["a"]
        pop["routes"]["a"]["status"] = "waiting"
        pop["routes"]["new"] = route(produced=["credit"])
        second = round_schedule(pop)
        self.assertEqual(["b"], second["order"])
        self.assertEqual(1, second["round"])
        pop.update(second)
        pop["opportunities"] = ["a", "b"]
        third = round_schedule(pop)
        self.assertEqual(2, third["round"])
        self.assertEqual(["new", "b"], third["order"])

    def test_waiting_route_does_not_block_finished_route_next_round(self):
        pop = {"routes": {"slow": route("waiting"), "fast": route()},
               "round": 1, "round_members": ["slow", "fast"],
               "opportunities": ["slow", "fast"]}
        next_round = round_schedule(pop)
        self.assertEqual(2, next_round["round"])
        self.assertEqual(["fast"], next_round["order"])

    def test_low_score_still_gets_opportunity_and_rating_replays(self):
        pop = {"routes": {"low": route(), "high": route(produced=["x"])}}
        result = round_schedule(pop)
        self.assertEqual(["high", "low"], result["order"])
        self.assertTrue(replay_rating(result["rating"]))
        result["rating"]["order"] = ["low", "high"]
        self.assertFalse(replay_rating(result["rating"]))


if __name__ == "__main__":
    unittest.main()
