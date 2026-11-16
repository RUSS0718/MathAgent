"""Trusted entry and frozen public Run identity for initial Explore capacity."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from showcase.faithful_service_config import load_faithful_config
from showcase.solver_harness import SolverHarness
from showcase.storage import SQLiteStore
from tests.test_dependency_routing_recovery_190 import ROUTED_CONFIG
from tests.test_faithful_auto_intake import CONFIG, PROBLEM, SPEC
from tests.test_faithful_s03_job import CAPACITY_POLICY

VERSION = "initial-explore-v1-2048"
INITIAL_CONFIG = {**ROUTED_CONFIG, "initial_explore_policy_version": VERSION}


class InitialExploreConfigTest(unittest.TestCase):
    def test_new_policy_is_frozen_and_other_hash_mismatch_stays_strict(self):
        store = SQLiteStore()
        self.addCleanup(store.close)
        with SolverHarness(store=store, config=INITIAL_CONFIG) as harness:
            run = harness.solve(PROBLEM, {"run_id": "initial", "problem_spec": SPEC})
            self.assertEqual({"version": VERSION}, run["state"]["initial_explore_policy"])
            with self.assertRaisesRegex(ValueError, "initial_explore_policy_is_run_frozen"):
                harness.commit_event(run["run_id"], expected_revision=run["state_revision"],
                    event={"event_id": "change", "type": "config_changed"},
                    state_updates={"initial_explore_policy": None})
        for config in (ROUTED_CONFIG, {**INITIAL_CONFIG, "max_model_calls": 99}):
            with SolverHarness(store=store, config=config) as harness:
                with self.assertRaisesRegex(ValueError, "different config"):
                    harness.get_run("initial")
        with SolverHarness(store=store, config=INITIAL_CONFIG) as harness:
            self.assertEqual(run["state"]["config_hash"], harness.get_run("initial")["state"]["config_hash"])

    def test_legacy_and_190_runs_keep_key_absent(self):
        for config in (CONFIG, ROUTED_CONFIG):
            with self.subTest(config=config), SolverHarness(config=config) as harness:
                run = harness.solve(PROBLEM, {"problem_spec": SPEC})
                self.assertNotIn("initial_explore_policy", run["state"])

    def test_unknown_version_or_missing_routing_is_rejected(self):
        for invalid in (None, False, "future", 2048):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError,
                    "initial_explore_policy_version_invalid"):
                SolverHarness(config={**ROUTED_CONFIG, "initial_explore_policy_version": invalid})
        with self.assertRaisesRegex(ValueError, "initial_explore_requires_dependency_routing"):
            SolverHarness(config={**CONFIG, "initial_explore_policy_version": VERSION})

    def test_trusted_json_only_adds_explicit_policy_key(self):
        value = {"version": "faithful-service-v1", "python_image_id": "sha256:" + "a" * 64,
                 "context_capacity": CAPACITY_POLICY, "adaptive_solving": True,
                 "routing_policy_version": "objective-dependency-routing-v1",
                 "budget": {"max_model_calls": 48, "max_http_attempts": 48,
                            "max_tool_calls": 8, "max_tokens": 262144, "max_runtime_seconds": 1100}}
        with TemporaryDirectory() as directory:
            path = Path(directory) / "service.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            old = load_faithful_config(path)
            self.assertNotIn("SHOWCASE_STAR_INITIAL_EXPLORE_POLICY_VERSION", old)
            value["initial_explore_policy_version"] = VERSION
            path.write_text(json.dumps(value), encoding="utf-8")
            new = load_faithful_config(path)
            self.assertEqual(VERSION, new.pop("SHOWCASE_STAR_INITIAL_EXPLORE_POLICY_VERSION"))
            self.assertEqual(old["SHOWCASE_STAR_FULL_FEATURES"], new["SHOWCASE_STAR_FULL_FEATURES"])
            self.assertEqual(old["SHOWCASE_STAR_FULL_BUDGET"], new["SHOWCASE_STAR_FULL_BUDGET"])
            value["initial_explore_policy_version"] = None
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "initial_explore_policy_version_invalid"):
                load_faithful_config(path)
