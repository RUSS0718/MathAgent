"""Public contracts for durable S10 same-checkpoint intervention state."""

import json
import sqlite3
import tempfile
import threading
import unittest
from copy import deepcopy
from pathlib import Path


class FaithfulInterventionRegistrationTest(unittest.TestCase):
    def test_constructor_does_not_commit_callers_open_transaction(self):
        from showcase.solver_harness.faithful_intervention import FaithfulInterventionEngine

        connection = sqlite3.connect(":memory:")
        self.addCleanup(connection.close)
        connection.execute("CREATE TABLE caller_state (value TEXT)")
        connection.commit()
        connection.execute("INSERT INTO caller_state VALUES ('uncommitted')")
        self.assertTrue(connection.in_transaction)
        FaithfulInterventionEngine(connection)
        self.assertTrue(connection.in_transaction)
        connection.rollback()
        self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM caller_state").fetchone()[0])
        self.assertEqual(0, connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name='faithful_intervention_pairs'"
        ).fetchone()[0])

    def test_unknown_transport_failure_is_not_registered_as_causal_hypothesis(self):
        from showcase.solver_harness.faithful_intervention import (
            FaithfulInterventionEngine,
            FaithfulInterventionError,
        )

        connection = sqlite3.connect(":memory:")
        self.addCleanup(connection.close)
        engine = FaithfulInterventionEngine(connection)
        for category in ("unknown_outcome", "transport_failure", "timeout"):
            with self.subTest(category=category):
                with self.assertRaisesRegex(FaithfulInterventionError, "hypothesis_category_noncausal"):
                    engine.register_hypothesis({
                        "hypothesis_id": category, "failure_category": category,
                        "evidence": {"call_id": "call-1"},
                        "candidate_action_ids": ("a", "b"),
                        "falsification_criteria": {"check": "review"},
                    })

    def test_hypotheses_and_actions_are_durable_and_share_registration_transaction(self):
        from showcase.solver_harness.faithful_intervention import (
            FailureHypothesis,
            FaithfulInterventionEngine,
            ProofAction,
        )

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "intervention.sqlite3"
            connection = sqlite3.connect(database, check_same_thread=False)
            connection.execute("CREATE TABLE workspace_actions (action_id TEXT PRIMARY KEY)")
            engine = FaithfulInterventionEngine(connection)
            hypothesis = FailureHypothesis(
                hypothesis_id="hyp-1",
                failure_category="invalid_inference",
                evidence={"event_id": "review-4", "reason": "unsupported step"},
                candidate_action_ids=("control", "intervention"),
                falsification_criteria={"condition": "review accepts same step"},
            )
            control = ProofAction("control", "review_strategy", "step-4", {"mode": "direct"})
            intervention = ProofAction(
                "intervention", "review_strategy", "step-4", {"mode": "decompose"}
            )

            def action_hook(db):
                db.execute("INSERT INTO workspace_actions VALUES (?)", ("register-hyp-1",))

            engine.register_hypothesis(hypothesis)
            engine.register_action(control)
            engine.register_action(intervention, transaction_hook=action_hook)
            connection.close()

            reopened = sqlite3.connect(database, check_same_thread=False)
            restored = FaithfulInterventionEngine(reopened)
            self.assertEqual(hypothesis, restored.get_hypothesis("hyp-1"))
            self.assertEqual(control, restored.get_action("control"))
            self.assertEqual(intervention, restored.get_action("intervention"))
            self.assertEqual(
                ("register-hyp-1",),
                reopened.execute("SELECT action_id FROM workspace_actions").fetchone(),
            )
            reopened.close()

    def test_registration_hook_failure_rolls_back_registered_action(self):
        from showcase.solver_harness.faithful_intervention import (
            FaithfulInterventionEngine,
            ProofAction,
        )

        connection = sqlite3.connect(":memory:")
        engine = FaithfulInterventionEngine(connection)
        action = ProofAction("action", "review_strategy", "step-1", {"mode": "direct"})

        def fail(_connection):
            raise RuntimeError("workspace action insert failed")

        with self.assertRaisesRegex(RuntimeError, "workspace action insert failed"):
            engine.register_action(action, transaction_hook=fail)
        with self.assertRaises(KeyError):
            engine.get_action("action")
        connection.close()

    def test_identical_registration_still_commits_new_workspace_idempotency_hook(self):
        from showcase.solver_harness.faithful_intervention import (
            FaithfulInterventionEngine,
            ProofAction,
        )

        connection = sqlite3.connect(":memory:")
        self.addCleanup(connection.close)
        engine = FaithfulInterventionEngine(connection)
        action = ProofAction("action", "review_strategy", "step-1", {"mode": "direct"})
        engine.register_action(action)
        connection.execute("CREATE TABLE workspace_actions (key TEXT PRIMARY KEY)")
        engine.register_action(
            action,
            transaction_hook=lambda db: db.execute(
                "INSERT INTO workspace_actions VALUES ('new-request-key')"
            ),
        )
        self.assertEqual(
            ("new-request-key",),
            connection.execute("SELECT key FROM workspace_actions").fetchone(),
        )


class FaithfulInterventionReservationTest(unittest.TestCase):
    def setUp(self):
        from showcase.run_budget import RunBudgetLedger, RunBudgetLimits
        from showcase.solver_harness import SolverHarness
        from showcase.solver_harness.faithful_intervention import FaithfulInterventionEngine
        from showcase.storage import SQLiteStore

        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "pair.sqlite3"
        self.store = SQLiteStore(self.path)
        self.addCleanup(self.store.close)
        self.connection = self.store._connection
        self.lock = threading.RLock()
        with SolverHarness(store=self.store, config={"profile": "test"}) as harness:
            self.parent = harness.solve("2+2", {"run_id": "parent-run"})
            self.parent = harness.commit_event(
                "parent-run", expected_revision=self.parent["state_revision"],
                event={"event_id": "checkpoint", "type": "checkpoint_committed"},
                state_updates={"checkpoint_marker": "cp-1"},
            )
        self.ledger = RunBudgetLedger(connection=self.connection, lock=self.lock)
        self.ledger.ensure("parent-run", RunBudgetLimits(
            max_model_calls=8, max_http_attempts=8, max_tool_calls=4,
            max_tokens=1000, max_runtime_seconds=120,
        ))
        self.engine = FaithfulInterventionEngine(self.connection, connection_lock=self.lock)
        self.engine.register_hypothesis({
            "hypothesis_id": "hyp-1", "failure_category": "invalid_inference",
            "evidence": {"event_id": "checkpoint"},
            "candidate_action_ids": ("control", "intervention", "two-differences"),
            "falsification_criteria": {"condition": "same result after review"},
        })
        for action_id, mode, depth in (("control", "direct", 1),
                                       ("intervention", "decompose", 1),
                                       ("two-differences", "decompose", 2)):
            self.engine.register_action({
                "action_id": action_id, "action_type": "review_strategy", "target": "step-4",
                "parameters": {"mode": mode, "depth": depth},
            })
        self.gate = _PausedParentGate()

    def tearDown(self):
        self.store.close()
        self.temporary.cleanup()

    def reserve(self, **changes):
        args = dict(
            job_id="job-1", job_gate=self.gate, run_id="parent-run",
            expected_revision=self.parent["state_revision"], hypothesis_id="hyp-1",
            control_action_id="control", intervention_action_id="intervention",
            pair_id="pair-1", seed=17,
            reservation={"input_estimate": 10, "output_cap": 20},
        )
        args.update(changes)
        return self.engine.reserve_pair(**args)

    def test_atomic_symmetric_holds_preserve_checkpoint_and_original_deadline(self):
        from showcase.solver_harness.storage import SolverStateStore

        before = deepcopy(SolverStateStore(self.connection).get_run("parent-run"))
        deadline = self.ledger.snapshot("parent-run")["deadline_at"]
        pair = self.reserve()
        self.assertEqual(before, SolverStateStore(self.connection).get_run("parent-run"))
        self.assertEqual("reserved", pair["status"])
        self.assertEqual(0, pair["started_pairs"])
        self.assertIsNone(pair["effect"])
        self.assertEqual(["control", "intervention"], sorted(pair["order"]))
        self.assertNotEqual(pair["arms"]["control"]["branch_id"],
                            pair["arms"]["intervention"]["branch_id"])
        snapshot = self.ledger.snapshot("parent-run")
        self.assertEqual((2, 2, 60),
                         (snapshot["logical_calls"], snapshot["http_attempts"],
                          snapshot["charged_tokens"]))
        self.assertEqual(0, snapshot["unknown_attempts"])
        self.assertEqual(60, snapshot["reserved_tokens"])
        self.assertEqual({"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                         snapshot["provider_known"])
        self.assertEqual([], self.ledger.attempts("parent-run"))
        self.assertEqual(
            {"control": "faithful_intervention:pair-1:control",
             "intervention": "faithful_intervention:pair-1:intervention"},
            pair["budget_reservation"]["arm_roles"],
        )
        self.assertEqual(deadline, snapshot["deadline_at"])
        self.assertEqual(self.parent["state_revision"], pair["checkpoint_revision"])
        checkpoint = json.loads(self.connection.execute(
            "SELECT checkpoint_json FROM faithful_intervention_pairs WHERE pair_id='pair-1'"
        ).fetchone()[0])
        self.assertEqual(before["state"], checkpoint["state"])
        self.assertEqual(self.parent["state_revision"], checkpoint["state_revision"])
        self.assertEqual(pair, self.engine.get_pair("pair-1"))
        self.assertEqual(pair, self.reserve())
        self.assertEqual(2, self.ledger.snapshot("parent-run")["logical_calls"])

    def test_stale_checkpoint_multiple_changes_and_unpaused_parent_reject(self):
        from showcase.solver_harness.faithful_intervention import FaithfulInterventionError

        for changes, reason in (
            ({"expected_revision": self.parent["state_revision"] + 1}, "checkpoint_revision"),
            ({"intervention_action_id": "two-differences"}, "single_action_difference"),
        ):
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(FaithfulInterventionError, reason):
                    self.reserve(**changes)
        self.gate.paused = False
        with self.assertRaisesRegex(RuntimeError, "job_not_paused"):
            self.reserve()
        self.assertEqual(0, self.ledger.snapshot("parent-run")["logical_calls"])

    def test_insufficient_budget_reserves_neither_arm(self):
        from showcase.run_budget import BudgetExhausted

        with self.assertRaises(BudgetExhausted):
            self.reserve(reservation={"input_estimate": 600, "output_cap": 20})
        self.assertEqual(0, self.ledger.snapshot("parent-run")["http_attempts"])
        with self.assertRaises(KeyError):
            self.engine.get_pair("pair-1")

    def test_workspace_hook_failure_rolls_back_pair_and_entire_budget(self):
        self.connection.execute("CREATE TABLE workspace_actions (key TEXT PRIMARY KEY)")
        before = self.ledger.snapshot("parent-run")["charged_tokens"]

        def fail(connection):
            connection.execute("INSERT INTO workspace_actions VALUES ('pair-idem')")
            raise RuntimeError("workspace action failed")

        with self.assertRaisesRegex(RuntimeError, "workspace action failed"):
            self.reserve(transaction_hook=fail)
        self.assertEqual(before, self.ledger.snapshot("parent-run")["charged_tokens"])
        self.assertEqual(0, self.connection.execute(
            "SELECT COUNT(*) FROM workspace_actions").fetchone()[0])
        with self.assertRaises(KeyError):
            self.engine.get_pair("pair-1")

    def test_persisted_pair_recovers_without_executing_and_conflicting_retry_rejects(self):
        from showcase.solver_harness.faithful_intervention import (
            FaithfulInterventionEngine,
            FaithfulInterventionError,
        )
        from showcase.storage import SQLiteStore

        self.connection.execute("CREATE TABLE workspace_actions (key TEXT PRIMARY KEY)")
        saved = self.reserve(transaction_hook=lambda db: db.execute(
            "INSERT INTO workspace_actions VALUES ('pair-request')"
        ))
        self.assertEqual(("pair-request",), tuple(self.connection.execute(
            "SELECT key FROM workspace_actions"
        ).fetchone()))
        with SQLiteStore(self.path) as store:
            engine = FaithfulInterventionEngine(store._connection)
            self.assertEqual(saved, engine.get_pair("pair-1"))
        with self.assertRaisesRegex(FaithfulInterventionError, "pair_identity_conflict"):
            self.reserve(seed=18)
        self.assertEqual(2, self.ledger.snapshot("parent-run")["logical_calls"])

    def test_terminal_solver_rejects_even_if_caller_gate_accepts(self):
        from showcase.solver_harness import SolverHarness
        from showcase.solver_harness.faithful_intervention import FaithfulInterventionError

        with SolverHarness(store=self.store, config={"profile": "test"}) as harness:
            terminal = harness.commit_event(
                "parent-run", expected_revision=self.parent["state_revision"],
                event={"event_id": "terminal", "type": "stopped"},
                state_updates={"phase": "TERMINAL", "status": "completed"},
            )
        with self.assertRaisesRegex(FaithfulInterventionError, "parent_run_terminal"):
            self.reserve(expected_revision=terminal["state_revision"])

    def test_expired_parent_deadline_rejects_without_reset(self):
        from showcase.run_budget import BudgetExhausted, RunBudgetLimits

        self.ledger.ensure("expired", RunBudgetLimits(), deadline_at=1)
        with self.connection:
            self.connection.execute("UPDATE run_budgets SET ledger_json=(SELECT ledger_json "
                                    "FROM run_budgets WHERE run_id='expired') "
                                    "WHERE run_id='parent-run'")
        with self.assertRaises(BudgetExhausted):
            self.reserve()
        self.assertEqual(1, self.ledger.snapshot("parent-run")["deadline_at"])


class _PausedParentGate:
    def __init__(self):
        self.paused = True

    def assert_paused(self, *, connection, job_id, run_id, checkpoint_revision):
        if not self.paused:
            raise RuntimeError("job_not_paused")
