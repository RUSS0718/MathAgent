"""Offline execution and settlement contracts; no provider or product Job claims."""

import tempfile
import threading
import unittest
from pathlib import Path


class _PausedParentGate:
    def assert_paused(self, *, connection, job_id, run_id, checkpoint_revision):
        del connection, job_id, run_id, checkpoint_revision


class InterventionExecutionTest(unittest.TestCase):
    def setUp(self):
        from showcase.run_budget import RunBudgetLedger, RunBudgetLimits
        from showcase.solver_harness import SolverHarness
        from showcase.solver_harness.faithful_intervention import FaithfulInterventionEngine
        from showcase.storage import SQLiteStore

        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = SQLiteStore(Path(self.temporary.name) / "pair.sqlite3")
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

    def execute(self, executor):
        self.reserve()
        return self.engine.execute_pair(
            "pair-1", execute_branch=executor, ledger=self.ledger, job_gate=self.gate,
        )

    def test_branches_execute_once_from_identical_checkpoint_with_actual_parent_settlement(self):
        from showcase.run_budget import current_budget
        from showcase.solver_harness.faithful_intervention_records import BranchOutcome
        from showcase.solver_harness.storage import SolverStateStore

        seen = []
        before = SolverStateStore(self.connection).get_run("parent-run")

        def executor(*, checkpoint, action, branch_id, arm, budget, budget_role):
            self.assertIs(current_budget(), budget)
            self.assertNotIn("private_branch", checkpoint["state"])
            self.assertEqual(before["state"], checkpoint["state"])
            checkpoint["state"]["private_branch"] = arm
            seen.append((arm, action.action_id))
            call = budget.model_call("reasoner")
            event = {"attempt_id": branch_id + ":attempt", "max_tokens": 20}
            call.before_attempt(event, input_estimate=10)
            call.after_attempt({**event, "status": "success", "http_status": 200,
                                "prompt_tokens": 4, "completion_tokens": 3,
                                "total_tokens": 7})
            return BranchOutcome("completed", 1 if arm == "control" else 3,
                                 {"receipt": arm, "api_key": "must-not-persist"},
                                 ({"event_id": "one", "type": "observed",
                                   "prompt": "must-not-persist"},))

        report = self.execute(executor)
        self.assertEqual([arm for arm in report["order"]], [item[0] for item in seen])
        self.assertEqual(1, report["denominator"])
        self.assertEqual(1, report["evaluable_pairs"])
        self.assertEqual(2, report["effect"]["measurement_delta"])
        self.assertEqual("external_adapter", report["branch_engine"])
        self.assertEqual("unavailable", report["parent_resume"])
        self.assertIsNone(report["effect"]["interval"])
        self.assertEqual(14, self.ledger.snapshot("parent-run")["provider_known"]["total_tokens"])
        self.assertEqual(2, self.ledger.snapshot("parent-run")["http_attempts"])
        self.assertEqual(before, SolverStateStore(self.connection).get_run("parent-run"))
        persisted = str(self.engine.get_pair("pair-1"))
        self.assertNotIn("must-not-persist", persisted)
        self.assertEqual(report, self.engine.execute_pair(
            "pair-1", execute_branch=executor, ledger=self.ledger, job_gate=self.gate))
        self.assertEqual(2, len(seen))

    def test_unknown_keeps_denominator_hold_and_no_imputed_effect(self):
        from showcase.solver_harness.faithful_intervention_records import BranchOutcome

        def executor(*, arm, budget, branch_id, **_):
            call = budget.model_call("reasoner")
            event = {"attempt_id": branch_id + ":attempt", "max_tokens": 20}
            call.before_attempt(event, input_estimate=10)
            if arm == "control":
                call.after_attempt({**event, "status": "unknown", "error_category": "timeout"})
                return BranchOutcome("unknown_outcome")
            call.after_attempt({**event, "status": "success", "prompt_tokens": 4,
                                "completion_tokens": 3, "total_tokens": 7})
            return BranchOutcome("completed", 3)

        report = self.execute(executor)
        self.assertEqual(1, report["denominator"])
        self.assertEqual(1, report["unknown_pairs"])
        self.assertEqual(0, report["evaluable_pairs"])
        self.assertIsNone(report["effect"])
        self.assertEqual(30, self.ledger.snapshot("parent-run")["reserved_tokens"])
        self.assertEqual(1, self.ledger.snapshot("parent-run")["unknown_attempts"])

    def test_unexecuted_result_is_incomplete_and_never_counts_as_effect(self):
        from showcase.solver_harness.faithful_intervention_records import BranchOutcome

        report = self.execute(lambda **_: BranchOutcome("completed", 10))
        self.assertEqual(1, report["denominator"])
        self.assertEqual(1, report["incomplete_pairs"])
        self.assertEqual(0, report["evaluable_pairs"])
        self.assertIsNone(report["effect"])

    def test_explicit_unknown_without_http_dispatch_remains_unknown(self):
        from showcase.solver_harness.faithful_intervention_records import BranchOutcome

        report = self.execute(lambda **_: BranchOutcome("unknown_outcome"))
        self.assertEqual(1, report["denominator"])
        self.assertEqual(1, report["unknown_pairs"])
        self.assertEqual(0, report["incomplete_pairs"])
        self.assertIsNone(report["effect"])

    def test_interrupted_execution_read_recovers_unknown_without_redispatch(self):
        def executor(**_):
            raise KeyboardInterrupt()

        self.reserve()
        with self.assertRaises(KeyboardInterrupt):
            self.engine.execute_pair("pair-1", execute_branch=executor,
                                     ledger=self.ledger, job_gate=self.gate)
        report = self.engine.get_pair("pair-1")
        self.assertEqual(1, report["denominator"])
        self.assertEqual(1, report["unknown_pairs"])
        self.assertIsNone(report["effect"])
        self.engine.execute_pair("pair-1", execute_branch=lambda **_: self.fail("redispatch"),
                                 ledger=self.ledger, job_gate=self.gate)

    def test_second_action_and_cross_arm_settlement_are_rejected(self):
        from showcase.run_budget import BudgetExhausted
        from showcase.solver_harness.faithful_intervention_records import (
            BranchOutcome,
            FaithfulInterventionError,
        )

        def executor(*, arm, budget, branch_id, **_):
            call = budget.model_call("reasoner")
            with self.assertRaises(BudgetExhausted):
                budget.model_call("reasoner")
            event = {"attempt_id": branch_id + ":attempt", "max_tokens": 20}
            call.before_attempt(event, input_estimate=10)
            with self.assertRaises(BudgetExhausted):
                call.before_attempt({"attempt_id": "extra", "max_tokens": 20}, input_estimate=10)
            with self.assertRaises(FaithfulInterventionError):
                call.after_attempt({"attempt_id": "other-arm-attempt", "status": "success"})
            call.after_attempt({**event, "status": "success", "prompt_tokens": 4,
                                "completion_tokens": 3, "total_tokens": 7})
            return BranchOutcome("completed", 1)

        self.assertEqual(1, self.execute(executor)["evaluable_pairs"])

    def test_changed_checkpoint_rejects_before_executor(self):
        from showcase.solver_harness import SolverHarness
        from showcase.solver_harness.faithful_intervention_records import FaithfulInterventionError

        self.reserve()
        with SolverHarness(store=self.store, config={"profile": "test"}) as harness:
            harness.commit_event(
                "parent-run", expected_revision=self.parent["state_revision"],
                event={"event_id": "drift", "type": "changed"},
                state_updates={"checkpoint_marker": "cp-2"},
            )
        with self.assertRaises(FaithfulInterventionError):
            self.engine.execute_pair("pair-1", execute_branch=lambda **_: self.fail("dispatch"),
                                     ledger=self.ledger, job_gate=self.gate)

    def test_late_usage_settles_parent_without_upgrading_unknown_effect(self):
        from showcase.solver_harness.faithful_intervention_records import BranchOutcome

        receipts = []
        def executor(*, arm, budget, branch_id, **_):
            call = budget.model_call("reasoner")
            event = {"attempt_id": branch_id + ":attempt", "max_tokens": 20}
            call.before_attempt(event, input_estimate=10)
            call.after_attempt({**event, "status": "unknown", "error_category": "timeout"})
            receipts.append((call, event))
            return BranchOutcome("unknown_outcome")

        report = self.execute(executor)
        self.assertEqual(1, report["unknown_pairs"])
        for call, event in receipts:
            call.after_attempt({**event, "status": "success", "http_status": 200,
                                "prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7})
        self.assertEqual(14, self.ledger.snapshot("parent-run")["provider_known"]["total_tokens"])
        restored = self.engine.get_pair("pair-1")
        self.assertEqual(1, restored["unknown_pairs"])
        self.assertIsNone(restored["effect"])
        self.assertEqual(
            {"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7},
            restored["arms"]["control"]["cost"]["provider_usage"],
        )
