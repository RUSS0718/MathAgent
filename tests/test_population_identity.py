"""Population mode stays explicit and binds its complete Run budget."""

import unittest
from dataclasses import replace

from showcase.run_budget import RunBudgetLimits
from showcase.star_product_config import limited_config, population_config
from showcase.star_product_modes import mode_identity
from showcase.workspace import workspace_job_request_digest

CAPACITY = {
    "service_id": "test-provider",
    "max_inflight": 2,
    "worker_slots": 2,
    "evidence_ref": "controlled-test-fixture",
    "status": "controlled",
}


class PopulationIdentityTest(unittest.TestCase):
    def test_limited_config_rejects_concurrent_routes_without_population_preset(self):
        with self.assertRaisesRegex(ValueError, "star_population_preset"):
            limited_config(RunBudgetLimits(), {"concurrent_routes": True})

    def test_population_identity_changes_with_every_resource_budget(self):
        budget = RunBudgetLimits()

        def identity_for(limits):
            config = population_config(
                limits, CAPACITY, evidence_kind="fault_injection",
                request_timeout_seconds=15,
            )
            return mode_identity("star_population", config)

        def digest_for(limits):
            identity = identity_for(limits)
            return workspace_job_request_digest(
                session_id="session-1", message="problem", solver_mode="star_population",
                population_policy_hash=identity["population_policy_hash"],
            )

        baseline = identity_for(budget)["population_policy_hash"]
        baseline_digest = digest_for(budget)
        for field in (
            "max_model_calls", "max_http_attempts", "max_tool_calls",
            "max_tokens", "max_runtime_seconds",
        ):
            with self.subTest(resource_budget=field):
                delta = 0.5 if field == "max_runtime_seconds" else 1
                changed = identity_for(replace(budget, **{field: getattr(budget, field) + delta}))
                self.assertNotEqual(baseline, changed["population_policy_hash"])
                self.assertNotEqual(baseline_digest, digest_for(
                    replace(budget, **{field: getattr(budget, field) + delta})
                ))


if __name__ == "__main__":
    unittest.main()
