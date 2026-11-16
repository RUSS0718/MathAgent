"""Trusted configuration and frozen Run identity for dependency routing."""

import json
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from showcase.faithful_service_config import load_faithful_config
from showcase.solver_harness import SolverHarness
from tests.test_dependency_routing_recovery_190 import POLICY_VERSION, ROUTED_CONFIG
from tests.test_faithful_auto_intake import CONFIG, PROBLEM, SPEC
from tests.test_faithful_s03_job import CAPACITY_POLICY


class DependencyRoutingConfigTest(unittest.TestCase):
    def test_new_run_policy_is_frozen_against_public_state_mutation(self):
        with SolverHarness(config=ROUTED_CONFIG) as harness:
            run = harness.solve(PROBLEM, {"problem_spec": SPEC})
            self.assertEqual({"name": "objective-dependency-routing", "version": 1},
                             run["state"]["routing_policy"])
            with self.assertRaisesRegex(ValueError, "routing_policy_is_run_frozen"):
                harness.commit_event(run["run_id"], expected_revision=run["state_revision"],
                    event={"event_id": "change-policy", "type": "config_changed"},
                    state_updates={"routing_policy": None})

    def test_trusted_json_policy_is_explicit_and_does_not_change_other_options(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "service.json"
            value = {"version": "faithful-service-v1", "python_image_id": "sha256:" + "a" * 64,
                     "context_capacity": CAPACITY_POLICY,
                     "budget": {"max_model_calls": 48, "max_http_attempts": 48,
                                "max_tool_calls": 8, "max_tokens": 262144,
                                "max_runtime_seconds": 1100}, "adaptive_solving": True}
            path.write_text(json.dumps(value), encoding="utf-8")
            old = load_faithful_config(path)
            self.assertNotIn("SHOWCASE_STAR_ROUTING_POLICY_VERSION", old)
            value["routing_policy_version"] = POLICY_VERSION
            path.write_text(json.dumps(value), encoding="utf-8")
            new = load_faithful_config(path)
            self.assertEqual(POLICY_VERSION, new.pop("SHOWCASE_STAR_ROUTING_POLICY_VERSION"))
            self.assertEqual(old["SHOWCASE_STAR_FULL_FEATURES"], new["SHOWCASE_STAR_FULL_FEATURES"])
            self.assertEqual(old["SHOWCASE_STAR_FULL_BUDGET"], new["SHOWCASE_STAR_FULL_BUDGET"])
            for invalid in (None, False, 1, "future"):
                value["routing_policy_version"] = invalid
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "routing_policy_version_invalid"):
                    load_faithful_config(path)

    def test_other_config_changes_still_fail_identity_and_legacy_policy_stays_absent(self):
        from showcase.storage import SQLiteStore

        store = SQLiteStore()
        self.addCleanup(store.close)
        with SolverHarness(store=store, config=CONFIG) as harness:
            run = harness.solve(PROBLEM, {"run_id": "legacy", "problem_spec": SPEC})
            self.assertNotIn("routing_policy", run["state"])
        for changed in ({**CONFIG, "max_model_calls": 9}, ROUTED_CONFIG):
            with SolverHarness(store=store, config=changed) as harness:
                with self.assertRaisesRegex(ValueError, "different config"):
                    harness.get_run("legacy")
        with SolverHarness(store=store, config=CONFIG) as harness:
            self.assertEqual(run["state"]["config_hash"], harness.get_run("legacy")["state"]["config_hash"])

    def test_missing_required_feature_or_unknown_version_is_rejected_before_run_creation(self):
        for key in ("adaptive_solving", "problem_spec", "auto_problem_spec", "star_routing",
                    "final_generation", "final_solution_review"):
            config = deepcopy(ROUTED_CONFIG)
            config["features"][key] = False
            with self.subTest(feature=key), self.assertRaisesRegex(ValueError, "routing_policy_prerequisites_required"):
                SolverHarness(config=config)
        for version in (None, False, "future"):
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, "routing_policy_version_invalid"):
                SolverHarness(config={**ROUTED_CONFIG, "routing_policy_version": version})
