"""Pending workers must not be mistaken for completed controller work."""

import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

from showcase.run_control import RunStopped
from showcase.solver_harness.controller import advance_product


class PopulationControllerWaitTest(unittest.TestCase):
    def test_pending_waits_without_revision_progress_keep_control_checks(self):
        harness = SimpleNamespace(_population_futures={"action": object()})
        run = {"state_revision": 1, "state": {"phase": "POPULATION", "status": "running"}}
        calls = 0

        def advance(*args):
            nonlocal calls
            calls += 1
            if calls == 66:
                harness._population_futures.clear()
                return {"state_revision": 2, "state": {"phase": "TERMINAL", "status": "done"}}
            return deepcopy(run)

        with patch("showcase.solver_harness.controller.advance", side_effect=advance), patch(
                "showcase.run_control.check_control") as control:
            result = advance_product(harness, run, "problem")
        self.assertEqual("TERMINAL", result["state"]["phase"])
        self.assertEqual(66, control.call_count)

    def test_nonwaiting_transitions_keep_the_existing_limit(self):
        harness = SimpleNamespace(_population_futures={})
        run = {"state_revision": 1, "state": {"phase": "STEP_EXECUTE", "status": "running"}}

        def advance(_harness, current, *_args):
            return {**current, "state_revision": current["state_revision"] + 1}

        with patch("showcase.solver_harness.controller.advance", side_effect=advance) as step:
            result = advance_product(harness, run, "problem")
        self.assertEqual(64, step.call_count)
        self.assertEqual(65, result["state_revision"])

    def test_pending_wait_still_obeys_control_stop(self):
        harness = SimpleNamespace(_population_futures={"action": object()})
        run = {"state_revision": 1, "state": {"phase": "POPULATION", "status": "running"}}
        for category in ("run_canceled", "run_deadline_exhausted"):
            with self.subTest(category=category), patch(
                    "showcase.solver_harness.controller.advance", return_value=run), patch(
                    "showcase.run_control.check_control", side_effect=[None, RunStopped(category)]):
                with self.assertRaisesRegex(RunStopped, category):
                    advance_product(harness, run, "problem")
