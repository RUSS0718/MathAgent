"""Public route projection exposes numeric ratings and verifies stored replay."""
import unittest

from showcase.solver_harness.aprs import rate_routes
from showcase.star_product_summary import progress_summary


class RouteProjectionTest(unittest.TestCase):
    def test_numeric_projection_hides_inputs_and_rechecks_replay(self):
        state = {"route_policy": {"enabled": True, "policy_version": "serial-aprs-v1"},
                 "route_registry": [{"route_id": "r", "kind": "primary", "status": "active",
                                     "frontier_digest": "f", "frontier": [{"objective_id": "PRIVATE_GOAL"}]}],
                 "route_budget": {"closing_reserve": {"model_calls": 2, "PRIVATE": "secret"},
                                  "current_snapshot": {"charged_tokens": 25, "reserved_tokens": 4}}}
        evaluations, decision = rate_routes(state)
        state["route_evaluations"] = [{"evaluations": evaluations}]
        state["aprs_decisions"] = [decision]
        routes = progress_summary(state)["routes"]
        self.assertTrue(routes["decisions"][0]["replayable"])
        self.assertIsNone(routes["evaluations"][0]["vector"]["cost"])
        self.assertEqual(2, routes["budget"]["closing_reserve"]["model_calls"])
        self.assertNotIn("PRIVATE", repr(routes))
        state["route_registry"][0]["needs_reevaluation"] = True
        self.assertFalse(progress_summary(state)["routes"]["evaluations"][0]["hard_gate"])
        self.assertFalse(progress_summary(state)["routes"]["evaluations"][0]["current"])
        state["aprs_decisions"][0]["selected_route_id"] = "forged"
        self.assertFalse(progress_summary(state)["routes"]["decisions"][0]["replayable"])
