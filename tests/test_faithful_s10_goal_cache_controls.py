"""Lifecycle-only persistence tests; seeded rows do not establish L2 trust."""

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from showcase.solver_harness.faithful_goal_cache import GlobalGoalCache, GoalCacheIdentity


class GoalCacheControlsTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "cache.sqlite3"
        self.connection = sqlite3.connect(self.path)
        self.addCleanup(self.connection.close)
        self.cache = self._store(self.connection)
        self.cache.enable(actor_id="owner")
        self.connection.commit()
        self.identity = GoalCacheIdentity(
            goal={"target": "x=x"}, hypotheses=(), declarations=("polynomial_identity",),
            imports=("Mathlib.Tactic.Ring",), environment={"version": "fixture"},
            template_version="v1", axiom_policy=("propext",),
            specification_version=1, target_version="v1", proof_identity="source",
        )
        # Seed only the persisted lifecycle precondition, never the trust admission seam.
        self.connection.execute(
            """INSERT INTO faithful_goal_cache_entries VALUES (
                'fixture', 'owner', 'workspace', ?, ?, ?, 'active', NULL,
                'source', 'proof', 'target', 'environment', 'L2',
                'run', 'attempt', '2026-11-10', '2026-11-10')""",
            (self.identity.key, self.identity.lookup_key, json.dumps(self.identity.to_dict())),
        )
        self.connection.commit()

    @staticmethod
    def _store(connection):
        return GlobalGoalCache(connection, owner_id="owner", workspace_id="workspace")

    def _persisted(self, state, event):
        self.connection.close()
        with closing(sqlite3.connect(self.path)) as connection:
            cache = self._store(connection)
            self.assertEqual(state, cache.list_entries()[0]["state"])
            self.assertIn(event, [item["event"] for item in cache.list_audit_events()])

    def test_disabled_check_audit_survives_close(self):
        self.cache.disable(actor_id="owner")
        self.assertIsNone(self.cache.recheck(self.identity, {}, prover=None, actor_id="owner"))
        self._persisted("active", "receipt_check_suppressed")

    def test_key_drift_state_and_audit_survive_close(self):
        changed = replace(self.identity, environment={"version": "new"})
        result = self.cache.recheck(changed, {}, prover=None, actor_id="owner")
        self.assertEqual("stale", result["status"])
        self._persisted("stale", "receipt_stale")

    def test_untrusted_current_environment_state_and_audit_survive_close(self):
        result = self.cache.recheck(self.identity, {}, prover=None, actor_id="owner")
        self.assertEqual("current_lean_identity_untrusted", result["reason"])
        self._persisted("stale", "receipt_stale")

    def test_recheck_failure_state_and_audit_survive_close(self):
        class FailedProver:
            def invoke(self, request):
                raise RuntimeError("unavailable")

        with patch.object(GlobalGoalCache, "_check_identity"):
            result = self.cache.recheck(
                self.identity, {}, prover=FailedProver(), actor_id="owner"
            )
        self.assertEqual("lean_recheck_failed", result["reason"])
        self._persisted("stale", "receipt_stale")

    def test_oserror_during_recheck_is_rejected_and_persisted(self):
        class UnavailableProver:
            def invoke(self, request):
                raise OSError("lean container unavailable")

        with patch.object(GlobalGoalCache, "_check_identity"):
            result = self.cache.recheck(
                self.identity, {}, prover=UnavailableProver(), actor_id="owner"
            )
        self.assertEqual("stale", result["status"])
        self.assertEqual("lean_recheck_failed", result["reason"])
        self.assertNotIn("result", result)
        rejected = next(
            event for event in self.cache.list_audit_events()
            if event["event"] == "receipt_stale"
        )
        self.assertEqual("lean_recheck_failed", rejected["details"]["reason"])
        self._persisted("stale", "receipt_stale")

    def test_identity_drift_matrix_never_returns_the_old_receipt(self):
        changes = {
            "goal": {"target": "y=y"},
            "hypotheses": ("x : ℝ",),
            "declarations": ("different_theorem",),
            "imports": ("Mathlib.Data.Real.Basic",),
            "environment": {"version": "new", "dependency_audit": {"passed": False}},
            "template_version": "v2",
            "axiom_policy": ("Classical.choice",),
            "specification_version": 2,
            "target_version": "v2",
            "proof_identity": "new-source",
        }
        for field, value in changes.items():
            with self.subTest(field=field):
                connection = sqlite3.connect(":memory:")
                cache = self._store(connection)
                cache.enable(actor_id="owner")
                connection.execute(
                    """INSERT INTO faithful_goal_cache_entries VALUES (
                        'fixture', 'owner', 'workspace', ?, ?, ?, 'active', NULL,
                        'source', 'proof', 'target', 'environment', 'L2',
                        'run', 'attempt', '2026-11-10', '2026-11-10')""",
                    (self.identity.key, self.identity.lookup_key,
                     json.dumps(self.identity.to_dict())),
                )
                current = replace(self.identity, **{field: value})
                result = cache.recheck(current, {}, prover=None, actor_id="owner")
                self.assertFalse(
                    isinstance(result, dict) and result.get("status") == "rechecked"
                )
                self.assertFalse(isinstance(result, dict) and "result" in result)
                state = cache.list_entries()[0]["state"]
                if current.lookup_key == self.identity.lookup_key:
                    self.assertEqual("stale", state)
                    reasons = {
                        "declarations": "declaration_drift",
                        "imports": "import_dependency_drift",
                        "environment": "dependency_audit_drift",
                        "template_version": "template_drift",
                        "axiom_policy": "axiom_policy_drift",
                        "proof_identity": "proof_identity_drift",
                    }
                    reason = reasons.get(field)
                    if reason is not None:
                        self.assertEqual(reason, result["reason"])
                    else:
                        self.assertEqual("goal_cache_key_drift", result["reason"])
                else:
                    self.assertIsNone(result)
                    self.assertEqual("active", state)
                connection.close()

    def test_proof_drift_state_and_audit_survive_close(self):
        class DriftedProver:
            def invoke(self, request):
                return {"proof_artifact": {"proof_hash": "changed"}}

        with patch.object(GlobalGoalCache, "_check_identity"), patch.object(
            GlobalGoalCache, "_verified_grade", return_value="L2"
        ):
            result = self.cache.recheck(
                self.identity, {}, prover=DriftedProver(), actor_id="owner"
            )
        self.assertEqual("lean_proof_or_environment_drift", result["reason"])
        self._persisted("stale", "receipt_stale")

    def test_every_identity_dimension_drift_rejects_the_old_receipt(self):
        changes = {
            "goal": {"target": "y=y"},
            "hypotheses": ("x : ℝ",),
            "declarations": ("different_theorem",),
            "imports": ("Mathlib.Data.Real.Basic",),
            "environment": {"version": "new"},
            "template_version": "v2",
            "axiom_policy": ("Classical.choice",),
            "specification_version": 2,
            "target_version": "v2",
            "proof_identity": "new-source",
        }
        for field, value in changes.items():
            with self.subTest(field=field):
                connection = sqlite3.connect(":memory:")
                cache = self._store(connection)
                cache.enable(actor_id="owner")
                connection.execute(
                    """INSERT INTO faithful_goal_cache_entries VALUES (
                        'fixture', 'owner', 'workspace', ?, ?, ?, 'active', NULL,
                        'source', 'proof', 'target', 'environment', 'L2',
                        'run', 'attempt', '2026-11-10', '2026-11-10')""",
                    (self.identity.key, self.identity.lookup_key,
                     json.dumps(self.identity.to_dict())),
                )
                calls = []
                result = cache.recheck(
                    replace(self.identity, **{field: value}),
                    {}, prover=None, actor_id="owner",
                    invoke_current=lambda request: calls.append(request),
                )
                self.assertFalse(
                    isinstance(result, dict) and result.get("status") == "rechecked"
                )
                self.assertFalse(isinstance(result, dict) and "result" in result)
                self.assertEqual([], calls)
                connection.close()

    def test_clear_during_recheck_prevents_reuse(self):
        cache = self.cache

        class ClearingProver:
            def invoke(self, request):
                cache.clear(actor_id="owner")
                return {"grade": "L2", "proof_artifact": {
                    "source_hash": "source", "proof_hash": "proof",
                    "target_hash": "target", "environment_hash": "environment",
                }}

        with patch.object(GlobalGoalCache, "_check_identity"), patch.object(
            GlobalGoalCache, "_verified_grade", return_value="L2"
        ):
            result = cache.recheck(self.identity, {}, prover=ClearingProver(), actor_id="owner")
        self.assertEqual("invalidated", result["status"])
        self.assertNotIn("result", result)
        self._persisted("invalidated", "receipt_invalidated")

    def test_outer_rollback_owns_sidecar_writes(self):
        prior_audit = self.cache.list_audit_events()
        self.connection.execute("BEGIN")
        self.cache.clear(actor_id="owner")
        self.connection.rollback()
        self.assertEqual("active", self.cache.list_entries()[0]["state"])
        self.assertEqual(prior_audit, self.cache.list_audit_events())

    def test_missing_control_row_disables_admission(self):
        connection = sqlite3.connect(":memory:")
        self.addCleanup(connection.close)
        cache = self._store(connection)
        identity = replace(
            self.identity,
            goal={"target": {"hash": "target"}},
            environment={"deployment_manifest_sha256": "environment"},
            proof_identity="sha256:" + "b" * 64,
        )
        receipt = {
            "status": "solved", "grade": "L2",
            "proof_artifact": {
                "source_hash": "b" * 64, "proof_hash": "proof",
                "target_hash": "target", "environment_hash": "environment",
                "dependency_audit": {"passed": True, "recursive": True},
            },
        }
        with patch.object(GlobalGoalCache, "_check_identity"), patch.object(
            GlobalGoalCache, "_verified_grade", return_value="L2"
        ):
            with self.assertRaisesRegex(ValueError, "goal_cache_disabled"):
                cache.put_receipt(
                    identity, {"run_id": "run", "attempt_id": "attempt"},
                    receipt, prover=object(), actor_id="owner",
                )

    def test_untrusted_l3_claim_is_rejected_with_auditable_reason(self):
        connection = sqlite3.connect(":memory:")
        cache = self._store(connection)
        cache.enable(actor_id="owner")
        with self.assertRaisesRegex(ValueError, "goal_cache_requires_trusted_lean"):
            cache.put_receipt(
                self.identity,
                {"run_id": "run", "attempt_id": "attempt"},
                {"status": "solved", "grade": "L3", "proof_artifact": {}},
                prover=object(),
                actor_id="owner",
            )
        self.assertEqual([], cache.list_entries())
        event = next(
            item for item in cache.list_audit_events()
            if item["event"] == "receipt_rejected"
        )
        self.assertEqual("goal_cache_requires_trusted_lean", event["details"]["reason"])
        connection.close()
