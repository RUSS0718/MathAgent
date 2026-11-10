"""Formal pipeline uses Goal Cache only under exact owner/session opt-in."""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from showcase.formal import LeanTacticProver, normalize_target, register_formal
from showcase.formal_docker import LeanDockerExecutor, load_trusted_manifest
from showcase.run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget
from showcase.solver_harness.faithful_goal_cache import GlobalGoalCache
from showcase.solver_harness.formal_integration import (
    FormalIntegrationState,
    run_formal_verification,
)
from showcase.solver_harness.specification import normalize_problem_spec
from showcase.tools import ToolRegistry

PROBLEM = "For every rational x, (x + 1) ^ 2 = x ^ 2 + 2 * x + 1."
RAW_SPEC = {
    "specification_version": 1,
    "original_problem": PROBLEM,
    "domain": "rationals",
    "quantifiers": ["forall x"],
    "assumptions": [],
    "directions": ["equality"],
    "output_requirements": [],
    "root_obligations": [{
        "obligation_id": "root:identity",
        "obligation_type": "universal",
        "statement": "(x + 1) ^ 2 = x ^ 2 + 2 * x + 1",
    }],
    "auxiliary_goals": [],
}
RAW_TARGET = {
    "domain": "rationals",
    "variables": ["x"],
    "lhs": "(x + 1) ** 2",
    "rhs": "x ** 2 + 2 * x + 1",
    "quantifiers": ["forall x"],
    "assumptions": [],
    "direction": "equality",
}
POLICY = {
    "enabled": True,
    "backend": "lean_tactic_prover",
    "timeout_seconds": 30,
    "max_output_bytes": 1048576,
    "allowed_axioms": ["propext", "Classical.choice", "Quot.sound"],
    "environment": {},
}


def _state(job_id="job-1", run_id="run-1"):
    spec = normalize_problem_spec(RAW_SPEC)
    return FormalIntegrationState(
        job_id=job_id,
        run_id=run_id,
        problem=PROBLEM,
        problem_spec=spec,
        policy=POLICY,
        target=normalize_target(RAW_TARGET),
    )


def _trusted_lean():
    root = Path(__file__).resolve().parents[1]
    manifest_path = root / "artifacts" / "faithful-s09-environment-final-02" / "deployment.json"
    if not manifest_path.is_file() or shutil.which("docker") is None:
        raise unittest.SkipTest("the pinned Lean environment is unavailable")
    manifest = load_trusted_manifest(json.loads(manifest_path.read_text(encoding="utf-8")))
    image = subprocess.run(
        ["docker", "image", "inspect", manifest["image"], "--format", "{{.Id}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if image.returncode != 0:
        raise unittest.SkipTest("the pinned Lean image is unavailable")
    executor = LeanDockerExecutor(
        manifest=manifest, timeout_seconds=30, max_output_bytes=1048576
    )
    return LeanTacticProver(executor)


def _unavailable(request):
    return {
        "status": "unavailable",
        "grade": None,
        "attempt_id": request["attempt_id"],
        "parent_attempt_id": request["parent_attempt_id"],
        "proof_artifact": None,
        "specifications": {},
        "cost": {"elapsed_seconds": 0, "output_bytes": 0, "unknown": False},
    }


class GoalCacheFormalIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.execute(
            "CREATE TABLE workspace_jobs(job_id TEXT PRIMARY KEY, user_id TEXT, session_id TEXT, status TEXT)"
        )
        self.connection.execute(
            "INSERT INTO workspace_jobs VALUES ('job-1', 'owner-1', 'session-1', 'running')"
        )
        self.connection.commit()

    def tearDown(self):
        self.connection.close()

    def test_default_off_does_not_create_cache_tables_or_read_write_cache(self):
        class OrdinaryBackend:
            name = "ordinary_formal_backend"

            def invoke(self, request):
                return _unavailable(request)

        before = self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        result = run_formal_verification(
            _state(), backend=OrdinaryBackend(), target=normalize_target(RAW_TARGET),
            goal_cache_connection=self.connection,
        )
        after = self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()

        self.assertEqual("unavailable", result["status"])
        self.assertEqual(before, after)
        self.assertFalse(self.connection.in_transaction)

    def test_only_explicit_enabled_exact_owner_and_session_rechecks(self):
        backend = _trusted_lean()
        cache = GlobalGoalCache(
            self.connection, owner_id="owner-1", workspace_id="session-1"
        )
        cache.enable(actor_id="owner-1")
        self.connection.commit()
        calls = []
        original = GlobalGoalCache.recheck

        def observe_recheck(instance, identity, request, **kwargs):
            calls.append((instance.owner_id, instance.workspace_id, dict(request)))
            return original(instance, identity, request, **kwargs)

        backend.invoke = lambda request: _unavailable(request)
        with patch.object(GlobalGoalCache, "recheck", observe_recheck):
            result = run_formal_verification(
                _state(), backend=backend, target=normalize_target(RAW_TARGET),
                goal_cache_connection=self.connection,
            )

        self.assertEqual("unavailable", result["status"])
        self.assertEqual(1, len(calls))
        owner, workspace, request = calls[0]
        self.assertEqual(("owner-1", "session-1"), (owner, workspace))
        self.assertEqual("job-1", request["job_id"])
        self.assertEqual("run-1", request["run_id"])
        self.assertEqual([], cache.list_entries())
        self.assertEqual([], [e for e in cache.list_audit_events() if e["event"] == "receipt_admitted"])

    def test_wrong_scope_and_disabled_rows_do_not_construct_cache_or_recheck(self):
        backend = _trusted_lean()
        cache = GlobalGoalCache(
            self.connection, owner_id="owner-1", workspace_id="session-1"
        )
        cache.enable(actor_id="owner-1")
        GlobalGoalCache(
            self.connection, owner_id="owner-2", workspace_id="session-1"
        ).enable(actor_id="owner-2")
        self.connection.execute(
            "UPDATE faithful_goal_cache_control SET enabled=0 WHERE owner_id='owner-1'"
        )
        self.connection.commit()
        backend.invoke = lambda request: _unavailable(request)

        with patch.object(GlobalGoalCache, "recheck", side_effect=AssertionError("must skip")):
            result = run_formal_verification(
                _state(), backend=backend, target=normalize_target(RAW_TARGET),
                goal_cache_connection=self.connection,
            )

        self.assertEqual("unavailable", result["status"])
        self.assertEqual([], cache.list_entries())

    def test_untrusted_cache_hit_cannot_replace_formal_backend_verdict(self):
        backend = _trusted_lean()
        cache = GlobalGoalCache(
            self.connection, owner_id="owner-1", workspace_id="session-1"
        )
        cache.enable(actor_id="owner-1")
        self.connection.commit()
        normal_calls = []
        backend.invoke = lambda request: normal_calls.append(request) or _unavailable(request)
        forged = {
            "status": "solved",
            "grade": "L2",
            "attempt_id": "formal_attempt",
            "parent_attempt_id": None,
            "proof_artifact": {"source_hash": "forged"},
            "cost": {"elapsed_seconds": 0, "output_bytes": 0},
        }

        with patch.object(GlobalGoalCache, "recheck", return_value={
            "cache_id": "fixture", "status": "rechecked", "grade": "L2", "result": forged,
        }):
            result = run_formal_verification(
                _state(), backend=backend, target=normalize_target(RAW_TARGET),
                goal_cache_connection=self.connection,
            )

        self.assertEqual("unavailable", result["status"])
        self.assertIsNone(result["grade"])
        self.assertEqual(1, len(normal_calls))

    def test_cache_failure_does_not_change_verdict_or_commit_caller_transaction(self):
        backend = _trusted_lean()
        cache = GlobalGoalCache(
            self.connection, owner_id="owner-1", workspace_id="session-1"
        )
        cache.enable(actor_id="owner-1")
        self.connection.commit()
        backend.invoke = lambda request: _unavailable(request)
        self.connection.execute("BEGIN")

        with patch.object(GlobalGoalCache, "recheck", side_effect=sqlite3.OperationalError("locked")):
            result = run_formal_verification(
                _state(), backend=backend, target=normalize_target(RAW_TARGET),
                goal_cache_connection=self.connection,
            )

        self.assertEqual("unavailable", result["status"])
        self.assertTrue(self.connection.in_transaction)
        self.connection.rollback()

    def test_real_lean_admission_and_current_recheck_use_one_execution_each(self):
        backend = _trusted_lean()
        cache = GlobalGoalCache(
            self.connection, owner_id="owner-1", workspace_id="session-1"
        )
        cache.enable(actor_id="owner-1")
        self.connection.commit()
        state = _state()
        invocation = backend.invoke
        invocation_count = 0
        invocation_attempt_ids = []

        def count_invocation(request):
            nonlocal invocation_count
            invocation_count += 1
            invocation_attempt_ids.append(request["attempt_id"])
            return invocation(request)

        backend.invoke = count_invocation
        registry = ToolRegistry()
        register_formal(registry, backend)
        ledger = RunBudgetLedger(connection=self.connection)
        budget = ledger.ensure(
            "run-1",
            RunBudgetLimits(
                max_model_calls=4, max_http_attempts=4, max_tool_calls=4,
                max_tokens=100_000, max_runtime_seconds=120,
            ),
        )

        with bind_budget(budget):
            first = run_formal_verification(
                state, backend=backend, target=state.target, registry=registry,
                goal_cache_connection=self.connection,
            )
        self.assertEqual("solved", first["status"], first)
        self.assertEqual("L2", first["grade"], first)
        self.assertEqual(1, len(cache.list_entries()))
        invocation_count = 0
        with bind_budget(budget):
            second = run_formal_verification(
                state, backend=backend, target=state.target, registry=registry,
                goal_cache_connection=self.connection,
            )
        self.assertEqual("solved", second["status"], second)
        self.assertEqual("L2", second["grade"], second)
        self.assertEqual(1, invocation_count)
        self.assertEqual(2, budget.snapshot()["tool_calls"])
        self.assertEqual(
            [first["current"]["attempt_id"], second["current"]["attempt_id"]],
            invocation_attempt_ids,
        )
        self.assertNotEqual(first["current"]["attempt_id"], second["current"]["attempt_id"])
        events = [event["event"] for event in cache.list_audit_events()]
        self.assertIn("receipt_admitted", events)
        self.assertIn("receipt_rechecked", events)


if __name__ == "__main__":
    unittest.main()
