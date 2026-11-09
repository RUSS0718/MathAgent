"""Public contracts for the explicit concurrent Population Run preset."""

from __future__ import annotations

import json
import unittest

from showcase.run_budget import RunBudgetLimits
from showcase.star_product_config import limited_config, population_config
from showcase.star_product_modes import LIMITED_MODE_ORDER, mode_identity

CAPACITY = {
    "service_id": "controlled-http-fixture",
    "max_inflight": 2,
    "worker_slots": 2,
    "evidence_ref": "fixture:barrier-provider-v1",
    "status": "controlled",
}


class StarPopulationPresetTest(unittest.TestCase):
    """Keep concurrent Runs explicit, versioned, and capacity-bound."""

    def test_projection_counts_live_http_calls_separately_from_worker_slots(self):
        from showcase.solver_harness.population_projection import population_projection

        public = population_projection({
            "population": {"actions": {"work": {"status": "inflight"}}},
            "calls": {"call": {"action_id": "work", "status": "dispatched"}},
        })
        self.assertEqual(1, public["resources"]["http_inflight"])
        self.assertEqual(1, public["resources"]["worker_slots_in_use"])

    def test_population_mode_has_an_independent_versioned_identity(self) -> None:
        self.assertIn("star_population", LIMITED_MODE_ORDER)
        config = population_config(RunBudgetLimits(), CAPACITY, evidence_kind="fault_injection",
                                  request_timeout_seconds=15)

        identity = mode_identity("star_population", config)
        self.assertEqual("star_population", identity["solver_mode"])
        self.assertEqual("concurrent-aprs-v1", identity["preset_version"])
        self.assertEqual([], identity["missing_capabilities"])
        self.assertEqual(64, len(identity["population_policy_hash"]))
        self.assertEqual("population-v1", config["population_policy"]["schema_version"])
        self.assertTrue(config["population_policy"]["enabled"])
        self.assertTrue(config["features"]["concurrent_routes"])
        self.assertFalse(config["features"]["serial_routes"])
        for feature in (
            "problem_spec", "proof_graph", "progress_scheduling",
            "final_generation", "final_solution_review", "stream_recovery",
        ):
            self.assertTrue(config["features"][feature], feature)

    def test_ordinary_limited_preset_does_not_enable_concurrent_routes(self) -> None:
        config = limited_config(RunBudgetLimits())

        self.assertNotIn("concurrent_routes", config["features"])
        self.assertNotIn("population_policy", config)

    def test_unverified_or_untrusted_capacity_cannot_enable_population(self) -> None:
        variants = (
            ({**CAPACITY, "status": "not_measured"}, "fault_injection"),
            ({**CAPACITY, "status": "controlled"}, "live"),
            ({**CAPACITY, "worker_slots": 0}, "fault_injection"),
            ({**CAPACITY, "service_id": ""}, "fault_injection"),
        )
        for capacity, evidence_kind in variants:
            with self.subTest(capacity=capacity, evidence_kind=evidence_kind):
                with self.assertRaises(ValueError):
                    population_config(
                        RunBudgetLimits(), capacity, evidence_kind=evidence_kind,
                        request_timeout_seconds=15,
                    )

    def test_population_projection_counts_resources_and_drops_private_route_data(self) -> None:
        from showcase.solver_harness.population_projection import population_projection

        public = population_projection(
            {
                "population_policy": {
                    "enabled": True,
                    "version": "concurrent-aprs-v1",
                    "schema_version": "population-v1",
                    "capacity": CAPACITY,
                },
                "population": {
                    "owner": {"id": "SECRET_OWNER", "epoch": 3},
                    "epoch": 3,
                    "round": 4,
                    "round_members": ["SECRET_ROUTE_A", "SECRET_ROUTE_B"],
                    "opportunities": ["SECRET_ACTION_A"],
                    "routes": {
                        "SECRET_ROUTE_A": {
                            "status": "active",
                            "snapshot": {"prompt": "SECRET_PROMPT"},
                            "frontier_digest": "SECRET_FRONTIER",
                            "dependencies": ["SECRET_PROPOSITION"],
                        },
                        "SECRET_ROUTE_B": {"status": "waiting"},
                    },
                    "actions": {
                        "SECRET_ACTION_A": {
                            "status": "inflight",
                            "inflight": True,
                            "reservation": {
                                "opportunity": True,
                                "worker_slots": 1,
                                "http_inflight": 1,
                                "unknown": False,
                            },
                        },
                        "SECRET_ACTION_B": {
                            "status": "unknown",
                            "inflight": True,
                            "reservation": {
                                "opportunity": False,
                                "worker_slots": 0,
                                "http_inflight": 1,
                                "unknown": True,
                            },
                        },
                    },
                    "delivery": {"status": "delivered", "answer": "PRIVATE_ANSWER"},
                    "settlement": {"status": "pending", "request_id": "PRIVATE_REQUEST"},
                },
            }
        )

        encoded = json.dumps(public, ensure_ascii=False)
        for private in (
            "SECRET_", "PRIVATE_", "frontier_digest", "snapshot", "dependencies",
            "owner", "action_id", "route_id", "request_id", "service_id", "evidence_ref",
        ):
            self.assertNotIn(private, encoded)
        self.assertEqual(4, public["scheduler"]["round"])
        self.assertEqual(2, public["scheduler"]["member_count"])
        self.assertEqual(1, public["scheduler"]["opportunities_used"])
        self.assertEqual(1, public["resources"]["worker_slots_in_use"])
        self.assertEqual(2, public["resources"]["http_inflight"])
        self.assertEqual(1, public["resources"]["unknown_requests"])
        self.assertEqual("delivered", public["delivery"]["status"])
        self.assertEqual("pending", public["settlement"]["status"])


if __name__ == "__main__":
    unittest.main()
