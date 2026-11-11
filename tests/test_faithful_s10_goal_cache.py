"""AC22 tests for identity-complete, current-Lean-checked goal receipts."""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
import uuid
from dataclasses import replace
from pathlib import Path

from showcase.solver_harness.faithful_goal_cache import GlobalGoalCache, GoalCacheIdentity


def _base_identity():
    return GoalCacheIdentity(
        goal={"target": "x + 1 = x + 1"},
        hypotheses=("x : ℚ",),
        declarations=("polynomial_identity",),
        imports=("Mathlib",),
        environment={"image": "sha256:" + "a" * 64, "mathlib": "v1"},
        template_version="template-v1",
        axiom_policy=("propext", "Quot.sound"),
        specification_version="spec-v1",
        target_version="target-v1",
        proof_identity="sha256:" + "b" * 64,
    )


class GoalCacheIdentityTest(unittest.TestCase):
    def test_every_contract_dimension_contributes_to_the_key(self):
        original = _base_identity().key
        changes = (
            {"goal": {"target": "x + 1 = 2"}},
            {"hypotheses": ("x : ℝ",)},
            {"declarations": ("different_theorem",)},
            {"imports": ("Mathlib", "Mathlib.Data.Rat.Basic")},
            {"environment": {"image": "sha256:" + "c" * 64, "mathlib": "v1"}},
            {"template_version": "template-v2"},
            {"axiom_policy": ("propext",)},
            {"specification_version": "spec-v2"},
            {"target_version": "target-v2"},
            {"proof_identity": "sha256:" + "d" * 64},
        )
        for change in changes:
            with self.subTest(change=change):
                self.assertNotEqual(original, replace(_base_identity(), **change).key)

    def test_untrusted_prover_cannot_self_assert_l2(self):
        connection = sqlite3.connect(":memory:")
        cache = GlobalGoalCache(connection, owner_id="user-1", workspace_id="workspace-1")
        identity = _base_identity()
        request = {"run_id": "run-1", "attempt_id": "attempt-1"}

        class UntrustedProver:
            def verify_result(self, _request, _result):
                return "L2"

        with self.assertRaises(ValueError):
            cache.put_receipt(
                identity,
                request,
                {"status": "solved", "grade": "L2", "proof_artifact": {}},
                prover=UntrustedProver(),
                actor_id="user-1",
            )
        connection.close()


class RealLeanGoalCacheTest(unittest.TestCase):
    @staticmethod
    def _trusted_prover(test_case):
        root = Path(__file__).resolve().parents[1]
        manifest_path = root / "artifacts" / "faithful-s09-environment-final-02" / "deployment.json"
        if not manifest_path.is_file() or shutil.which("docker") is None:
            test_case.skipTest("the pinned local Lean image is unavailable")
        from showcase.formal import LeanTacticProver
        from showcase.formal_docker import LeanDockerExecutor, load_trusted_manifest

        manifest = load_trusted_manifest(json.loads(manifest_path.read_text(encoding="utf-8")))
        image = subprocess.run(
            ["docker", "image", "inspect", manifest["image"], "--format", "{{.Id}}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if image.returncode != 0:
            test_case.skipTest("the pinned local Lean image is unavailable")
        executor = LeanDockerExecutor(
            manifest=manifest,
            timeout_seconds=30,
            max_output_bytes=1048576,
        )
        return manifest, LeanTacticProver(executor)

    @staticmethod
    def _request(manifest, *, run_id, attempt_id):
        value = {
            "schema_version": 1,
            "job_id": "job-" + run_id,
            "run_id": run_id,
            "attempt_id": attempt_id,
            "parent_attempt_id": None,
            "problem": {
                "text": "Prove (x+1)^2 = x^2+2*x+1 for every rational x.",
                "hash": "",
            },
            "specification": {
                "specification_version": 1,
                "original_problem": "Prove (x+1)^2 = x^2+2*x+1 for every rational x.",
                "domain": "rationals",
                "quantifiers": ["forall x"],
                "assumptions": [],
                "directions": ["equality"],
                "output_requirements": [],
                "root_obligations": [{
                    "obligation_id": "root:identity",
                    "obligation_type": "universal",
                    "statement": "(x+1)^2 = x^2+2*x+1",
                }],
                "auxiliary_goals": [],
            },
            "target": {
                "domain": "rationals",
                "variables": ["x"],
                "lhs": "(x + 1) ** 2",
                "rhs": "x ** 2 + 2 * x + 1",
                "quantifiers": ["forall x"],
                "assumptions": [],
                "direction": "equality",
            },
            "policy": {
                "enabled": True,
                "backend": "lean_tactic_prover",
                "timeout_seconds": 30,
                "max_output_bytes": 1048576,
                "allowed_axioms": ["propext", "Classical.choice", "Quot.sound"],
                "environment": {},
            },
            "cost": {"elapsed_seconds": 0.0, "output_bytes": 0, "unknown": False},
            "review": None,
        }
        value["job_id"] = "job-" + run_id
        value["run_id"] = run_id
        value["attempt_id"] = attempt_id
        value["policy"]["environment"] = {
            "deployment_manifest_sha256": manifest["deployment_manifest_sha256"]
        }
        return value

    def test_real_l2_receipt_survives_restart_only_after_current_lean_recheck(self):
        manifest, prover = self._trusted_prover(self)
        request = self._request(
            manifest,
            run_id="run-" + uuid.uuid4().hex,
            attempt_id="attempt-" + uuid.uuid4().hex,
        )
        identity = GoalCacheIdentity.from_request(request, prover=prover)
        result = prover.invoke(request)
        self.assertEqual("L2", result["grade"], result)
        self.assertEqual("L2", prover.verify_result(request, result))

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "goal-cache.sqlite3"
            connection = sqlite3.connect(path)
            cache = GlobalGoalCache(connection, owner_id="user-1", workspace_id="workspace-1")
            cache.enable(actor_id="user-1")
            connection.commit()
            with self.assertRaisesRegex(ValueError, "goal_cache_result_not_trusted"):
                cache.put_receipt(
                    identity,
                    request,
                    {**result, "grade": "L1"},
                    prover=prover,
                    actor_id="user-1",
                )
            cache_id = cache.put_receipt(
                identity, request, result, prover=prover, actor_id="user-1"
            )
            other_user = GlobalGoalCache(
                connection, owner_id="user-2", workspace_id="workspace-1"
            )
            other_workspace = GlobalGoalCache(
                connection, owner_id="user-1", workspace_id="workspace-2"
            )
            self.assertEqual([], other_user.list_entries())
            self.assertEqual([], other_workspace.list_entries())
            with self.assertRaisesRegex(ValueError, "goal_cache_actor_mismatch"):
                cache.disable(actor_id="user-2")
            connection.close()

            reopened = sqlite3.connect(path)
            restored = GlobalGoalCache(
                reopened, owner_id="user-1", workspace_id="workspace-1"
            )
            current_manifest, current_prover = self._trusted_prover(self)
            current_request = self._request(
                current_manifest,
                run_id="run-" + uuid.uuid4().hex,
                attempt_id="attempt-" + uuid.uuid4().hex,
            )
            check = restored.recheck(
                identity,
                current_request,
                prover=current_prover,
                actor_id="user-1",
            )
            self.assertEqual(cache_id, check["cache_id"])
            self.assertEqual("rechecked", check["status"])
            self.assertEqual("L2", check["grade"])
            self.assertEqual(current_request["attempt_id"], check["result"]["attempt_id"])
            self.assertEqual(
                "L2", current_prover.verify_result(current_request, check["result"])
            )

            restored.disable(actor_id="user-1")
            self.assertIsNone(
                restored.recheck(
                    identity, current_request, prover=current_prover, actor_id="user-1"
                )
            )
            reopened.close()

            disabled_connection = sqlite3.connect(path)
            disabled = GlobalGoalCache(
                disabled_connection, owner_id="user-1", workspace_id="workspace-1"
            )
            disabled_events = disabled.list_audit_events()
            disabled_names = [event["event"] for event in disabled_events]
            self.assertIn("cache_disabled", disabled_names)
            self.assertIn("receipt_check_suppressed", disabled_names)
            self.assertTrue(next(
                event for event in disabled_events
                if event["event"] == "receipt_check_suppressed"
            )["details"]["tombstone"])
            disabled.enable(actor_id="user-1")
            current_prover.executor.manifest["dependency_audit"]["passed"] = False
            stale = disabled.recheck(
                identity, current_request, prover=current_prover, actor_id="user-1"
            )
            self.assertEqual("stale", stale["status"])
            disabled_connection.close()

            stale_connection = sqlite3.connect(path)
            stale_cache = GlobalGoalCache(
                stale_connection, owner_id="user-1", workspace_id="workspace-1"
            )
            self.assertEqual("stale", stale_cache.list_entries()[0]["state"])
            self.assertIn(
                "receipt_stale",
                [event["event"] for event in stale_cache.list_audit_events()],
            )
            stale_cache.invalidate(
                identity, actor_id="user-1", reason="operator_invalidation"
            )
            stale_cache.clear(actor_id="user-1")
            stale_connection.close()

            invalidated_connection = sqlite3.connect(path)
            invalidated = GlobalGoalCache(
                invalidated_connection, owner_id="user-1", workspace_id="workspace-1"
            )
            self.assertEqual("invalidated", invalidated.list_entries()[0]["state"])
            event_names = [event["event"] for event in invalidated.list_audit_events()]
            self.assertIn("receipt_invalidated", event_names)
            self.assertIn("cache_disabled", event_names)
            self.assertIn("cache_cleared", event_names)
            invalidated_connection.close()


if __name__ == "__main__":
    unittest.main()
