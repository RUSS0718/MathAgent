"""Dispatch guards after serial-route state changes."""
import unittest
from unittest.mock import Mock, patch

from showcase.solver_harness.challenge import run_challenges
from showcase.solver_harness.progress import guard_action


class RouteDispatchGuardTest(unittest.TestCase):
    def test_challenge_does_not_dispatch_after_guard_redirects_to_meta(self):
        run = {"state": {"phase": "CHALLENGE", "current_step": "s", "steps": {}}}
        redirected = {"state": {**run["state"], "phase": "META_DECIDE"}}
        model = Mock()
        with patch('showcase.solver_harness.progress.guard_action', return_value=redirected):
            result = run_challenges(Mock(), run, problem='p', model_port=model,
                                    verifier_port=Mock(), max_rounds=2,
                                    max_model_calls=10, max_runtime_seconds=100)
        self.assertEqual('META_DECIDE', result['state']['phase'])
        model.complete.assert_not_called()

    def test_graph_invalidated_route_is_stopped_before_execution(self):
        state = {"phase": "STEP_EXECUTE", "progress_policy": {"enabled": True},
                 "route_policy": {"enabled": True}, "active_route_id": "r",
                 "route_registry": [{"route_id": "r", "status": "active", "needs_reevaluation": True}]}
        run = {"run_id": "run", "state_revision": 4, "state": state}
        with patch('showcase.solver_harness.finalize.finish', return_value='stopped') as finish:
            result = guard_action(Mock(), run)
        self.assertEqual('stopped', result)
        self.assertEqual('route_requires_reevaluation', finish.call_args.args[-1])
