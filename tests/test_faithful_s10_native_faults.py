"""Fault-injection acceptance for native F4 execution on durable SQLite."""

import json
import unittest
from copy import deepcopy
from unittest.mock import patch

from tests import test_faithful_s03_job
from tests import test_faithful_s10_intervention_execution as support


class NativeFaultAcceptanceTest(unittest.TestCase):
    """Exercise native pair recovery and resource fencing with physical attempts."""

    setUp = support.InterventionExecutionTest.setUp

    def prepare_native_pair(self, *, reservation=None, config=None):
        """Create a valid paused native checkpoint and symmetric parent reservations."""
        from showcase.run_budget import RunBudgetLimits
        from showcase.solver_harness import SolverHarness
        from showcase.solver_harness.faithful_intervention_native import NativeCheckpointExecutor
        from showcase.solver_harness.faithful_intervention_records import ProofAction
        from showcase.solver_harness.routes import sync_plan_route

        config = config or {
            "max_model_calls": 20,
            "features": {
                "problem_spec": True,
                "progress_scheduling": True,
                "serial_routes": True,
                "final_generation": True,
                "final_solution_review": True,
                "proof_graph": True,
                "stream_recovery": True,
                "persistent_sessions": True,
            },
        }
        plan = deepcopy(test_faithful_s03_job.REPLIES[1])
        plan["steps"][0]["method_id"] = "direct"
        with SolverHarness(store=self.store, config=config) as harness:
            parent = harness.solve(test_faithful_s03_job.SPEC["original_problem"], {
                "run_id": "native-fault-parent",
                "problem_spec": test_faithful_s03_job.SPEC,
                "plan": plan,
            })
            parent = harness.commit_event(
                "native-fault-parent", expected_revision=parent["state_revision"],
                event={"event_id": "native-ready", "type": "initial_plan_generated"},
                state_updates={"phase": "STEP_EXECUTE", "plan": plan,
                               "plan_version": 1, "current_step": plan["steps"][0]["step_id"]},
            )
            parent = sync_plan_route(harness, parent)
        self.parent = parent
        self.config = config
        self.ledger.ensure("native-fault-parent", RunBudgetLimits(
            max_model_calls=20, max_http_attempts=20, max_tool_calls=4,
            max_tokens=30_000, max_runtime_seconds=120,
        ))
        for action_id, method_id in (("native-fault-control", "direct"),
                                     ("native-fault-variant", "induction")):
            self.engine.register_action(ProofAction(
                action_id, "reasoning_method", plan["steps"][0]["step_id"],
                {"method_id": method_id},
            ))
        self.engine.register_hypothesis({
            "hypothesis_id": "native-fault-hypothesis",
            "failure_category": "method_mismatch",
            "evidence": {"event_id": "native-ready"},
            "candidate_action_ids": ["native-fault-control", "native-fault-variant"],
            "falsification_criteria": {"condition": "no accepted root gain"},
        })
        pair_reservation = {
            "input_estimate": 1000, "output_cap": 1000,
            "model_calls": 3, "http_attempts": 1,
            "tool_calls": 1, "time_seconds": 20,
        }
        if reservation:
            pair_reservation.update(reservation)
        self.engine.reserve_pair(
            job_id="native-fault-parent", job_gate=self.gate,
            run_id="native-fault-parent", expected_revision=parent["state_revision"],
            hypothesis_id="native-fault-hypothesis",
            control_action_id="native-fault-control",
            intervention_action_id="native-fault-variant",
            pair_id="native-fault-pair", seed=29, reservation=pair_reservation,
        )
        return NativeCheckpointExecutor

    def make_port(self, *, attempts_per_call=1, rejected_verifier=False, challenge_verifier=False,
                  recheck_reject_arm=None, fault_arm=None, interrupt=False):
        """Return deterministic native ports that record physical budget attempts."""
        from showcase.run_budget import current_budget

        class Port:
            def __init__(inner):
                inner.calls = []

            def _attempt(inner, request):
                inner.calls.append((request["role"], request["call_id"]))
                budget = current_budget()
                call = budget.model_call(
                    request["role"], solver_call_id=request["call_id"])
                for index in range(attempts_per_call):
                    event = {"attempt_id": (
                                 f"{budget.ledger.branch_id}:{request['call_id']}:http:{index}"
                             ),
                             "max_tokens": 100}
                    call.before_attempt(event, input_estimate=100)
                    if (fault_arm and request["role"] == "reasoner"
                            and budget.ledger.branch_id.endswith(f":{fault_arm}")):
                        if interrupt:
                            raise KeyboardInterrupt("simulated process interruption")
                        call.after_attempt({**event, "status": "unknown",
                                            "error_category": "connectivity"})
                        raise ConnectionError("controlled connection loss after dispatch")
                    if index < attempts_per_call - 1:
                        call.after_attempt({**event, "status": "error",
                                            "error_category": "http_status", "http_status": 503,
                                            "prompt_tokens": 0, "completion_tokens": 0,
                                            "total_tokens": 0})
                    else:
                        call.after_attempt({**event, "status": "success", "http_status": 200,
                                            "prompt_tokens": 4, "completion_tokens": 3,
                                            "total_tokens": 7})

            def complete(inner, request):
                inner._attempt(request)
                return deepcopy(test_faithful_s03_job.REPLIES[2])

            def verify(inner, request):
                inner._attempt(request)
                if (recheck_reject_arm
                        and request["call_id"].endswith("-challenge-1")
                        and current_budget().ledger.branch_id.endswith(f":{recheck_reject_arm}")):
                    return {"goal_gate": "NO", "logic_gate": "FAIL",
                            "verdict": "CHALLENGE", "objection": "fresh review rejected"}
                if rejected_verifier:
                    return {"goal_gate": "NO", "logic_gate": "FAIL",
                            "verdict": "ACCEPT", "objection": "controlled rejection"}
                if challenge_verifier:
                    return {"goal_gate": "NO", "logic_gate": "FAIL",
                            "verdict": "CHALLENGE", "objection": "current step not established"}
                return deepcopy(test_faithful_s03_job.REPLIES[3])

        return Port()

    def executor_for(self, executor_type, port, *, config=None):
        """Bind one controlled port to the prepared checkpoint identity."""
        return executor_type(
            self.engine, config=config or self.config,
            problem=test_faithful_s03_job.SPEC["original_problem"],
            model_port=port, verifier_port=port,
        )

    def test_unknown_physical_attempt_keeps_parent_holds_and_checkpoint(self):
        from showcase.solver_harness.faithful_intervention_native import execute_native_pair
        from showcase.solver_harness.storage import SolverStateStore

        executor_type = self.prepare_native_pair()
        parent_before = SolverStateStore(self.connection).get_run("native-fault-parent")
        port = self.make_port(fault_arm="control")
        report = execute_native_pair(
            self.engine, "native-fault-pair",
            executor=self.executor_for(executor_type, port),
            ledger=self.ledger, job_gate=self.gate,
        )

        self.assertEqual(1, report["denominator"])
        self.assertEqual(1, report["unknown_pairs"])
        self.assertEqual("unknown_outcome", report["arms"]["control"]["status"])
        self.assertIsNone(report["effect"])
        self.assertEqual(1, self.ledger.snapshot("native-fault-parent")["unknown_attempts"])
        self.assertGreater(self.ledger.snapshot("native-fault-parent")["reserved_tokens"], 0)
        self.assertEqual(parent_before,
                         SolverStateStore(self.connection).get_run("native-fault-parent"))

    def test_restart_projects_interrupted_physical_dispatch_unknown_without_replay(self):
        from showcase.run_budget import RunBudgetLedger
        from showcase.solver_harness.faithful_intervention import FaithfulInterventionEngine
        from showcase.solver_harness.faithful_intervention_native import execute_native_pair
        from showcase.storage import SQLiteStore

        executor_type = self.prepare_native_pair()
        port = self.make_port(fault_arm="control", interrupt=True)
        executor = self.executor_for(executor_type, port)
        with self.assertRaises(KeyboardInterrupt):
            execute_native_pair(self.engine, "native-fault-pair", executor=executor,
                                ledger=self.ledger, job_gate=self.gate)
        physical_calls = len(port.calls)
        database_path = self.store.database_path
        self.store = SQLiteStore(database_path)
        self.addCleanup(self.store.close)
        self.connection = self.store._connection
        self.ledger = RunBudgetLedger(connection=self.connection, lock=self.lock)
        self.engine = FaithfulInterventionEngine(self.connection, connection_lock=self.lock)

        recovered = execute_native_pair(
            self.engine, "native-fault-pair", executor=executor,
            ledger=self.ledger, job_gate=self.gate,
        )

        self.assertEqual(physical_calls, len(port.calls), "restart must not resend a dispatched attempt")
        self.assertEqual(1, recovered["denominator"])
        self.assertEqual(1, recovered["unknown_pairs"])
        self.assertEqual("unknown_outcome", recovered["arms"]["control"]["status"])
        self.assertEqual(1, self.ledger.snapshot("native-fault-parent")["unknown_attempts"])

    def test_config_drift_is_rejected_before_pair_or_physical_dispatch(self):
        from showcase.solver_harness.faithful_intervention_native import execute_native_pair
        from showcase.solver_harness.faithful_intervention_records import FaithfulInterventionError

        executor_type = self.prepare_native_pair()
        port = self.make_port()
        changed = {**self.config, "max_model_calls": self.config["max_model_calls"] + 1}
        executor = self.executor_for(executor_type, port, config=changed)

        with self.assertRaises(FaithfulInterventionError):
            execute_native_pair(self.engine, "native-fault-pair", executor=executor,
                                ledger=self.ledger, job_gate=self.gate)

        self.assertEqual([], port.calls)
        self.assertEqual("reserved", self.engine.get_pair("native-fault-pair")["status"])

    def test_parent_state_drift_is_rejected_before_physical_dispatch(self):
        from showcase.solver_harness.faithful_intervention_native import execute_native_pair
        from showcase.solver_harness.faithful_intervention_records import FaithfulInterventionError

        executor_type = self.prepare_native_pair()
        port = self.make_port()
        state = json.loads(self.connection.execute(
            "SELECT state_json FROM solver_states WHERE run_id='native-fault-parent'"
        ).fetchone()[0])
        state["checkpoint_marker"] = "drifted"
        self.connection.execute(
            "UPDATE solver_states SET state_json=? WHERE run_id='native-fault-parent'",
            (json.dumps(state, sort_keys=True, separators=(",", ":")),),
        )
        self.connection.commit()

        with self.assertRaises(FaithfulInterventionError):
            execute_native_pair(
                self.engine, "native-fault-pair",
                executor=self.executor_for(executor_type, port),
                ledger=self.ledger, job_gate=self.gate,
            )

        self.assertEqual([], port.calls)

    def test_native_arm_rejects_cross_arm_settlement_and_excess_tool_claim(self):
        from showcase.run_budget import BudgetExhausted
        from showcase.solver_harness.faithful_intervention_native_budget import NativeArmLedger
        from showcase.solver_harness.faithful_intervention_records import FaithfulInterventionError

        self.prepare_native_pair()
        report = self.engine.get_pair("native-fault-pair")
        control = NativeArmLedger(self.ledger, report, "control", self.gate)
        intervention = NativeArmLedger(self.ledger, report, "intervention", self.gate)
        action_id, _ = intervention.reserve("native-fault-parent", "tool", attempt_id="other-arm-tool")

        with self.assertRaises(FaithfulInterventionError):
            control.settle("native-fault-parent", action_id, {"status": "success"})
        with self.assertRaises(BudgetExhausted):
            intervention.reserve("native-fault-parent", "tool", attempt_id="extra-tool")

    def test_native_arm_obeys_original_run_deadline(self):
        from showcase.run_budget import BudgetExhausted
        from showcase.solver_harness.faithful_intervention_native_budget import native_arm_budget

        self.prepare_native_pair(reservation={"time_seconds": 2})
        report = self.engine.get_pair("native-fault-pair")
        budget = native_arm_budget(self.ledger, report, "control", self.gate)
        self.assertEqual(budget.deadline_at, budget.snapshot()["deadline_at"])

        with patch("showcase.solver_harness.faithful_intervention_native_budget.time.time",
                   return_value=budget.deadline_at + 1):
            with self.assertRaises(BudgetExhausted):
                budget.ledger.reserve("native-fault-parent", "tool",
                                      attempt_id="after-deadline")

    def test_verifier_rejection_cannot_create_native_verified_gain(self):
        from showcase.solver_harness.faithful_intervention_native import execute_native_pair

        executor_type = self.prepare_native_pair()
        port = self.make_port(rejected_verifier=True)
        report = execute_native_pair(
            self.engine, "native-fault-pair",
            executor=self.executor_for(executor_type, port),
            ledger=self.ledger, job_gate=self.gate,
        )

        self.assertEqual(0, report["evaluable_pairs"])
        self.assertIsNone(report["effect"])
        self.assertIsNone(report["arms"]["control"]["measurement"])
        self.assertEqual([], report["arms"]["control"]["evidence"]["current_verified_gain"])
        self.assertEqual("not_accepted", report["arms"]["control"]["evidence"]["review"])

    def test_valid_challenge_is_not_counted_as_a_reviewed_completed_arm(self):
        from showcase.solver_harness.faithful_intervention_native import execute_native_pair

        executor_type = self.prepare_native_pair()
        port = self.make_port(challenge_verifier=True)
        report = execute_native_pair(
            self.engine, "native-fault-pair",
            executor=self.executor_for(executor_type, port),
            ledger=self.ledger, job_gate=self.gate,
        )

        self.assertEqual(0, report["evaluable_pairs"])
        self.assertEqual(1, report["incomplete_pairs"])
        self.assertEqual("incomplete", report["arms"]["control"]["status"])
        self.assertEqual("CHALLENGE", report["arms"]["control"]["branch_verifier_verdict"])
        self.assertEqual("not_checked", report["arms"]["control"]["evidence_integrity"])
        self.assertEqual([], report["arms"]["control"]["evidence"]["current_verified_gain"])

    def test_fresh_recheck_rejection_keeps_pair_incomplete_and_unmerged(self):
        from showcase.solver_harness.faithful_intervention_native import execute_native_pair

        executor_type = self.prepare_native_pair()
        port = self.make_port(recheck_reject_arm="control")
        parent_before = self.parent
        report = execute_native_pair(
            self.engine, "native-fault-pair",
            executor=self.executor_for(executor_type, port),
            ledger=self.ledger, job_gate=self.gate,
        )

        self.assertEqual(1, report["denominator"])
        self.assertEqual(0, report["evaluable_pairs"])
        self.assertEqual(1, report["incomplete_pairs"])
        self.assertIsNone(report["effect"])
        control = report["arms"]["control"]
        self.assertEqual("ACCEPT", control["branch_verifier_verdict"])
        self.assertEqual("CHALLENGE", control["independent_recheck_verdict"])
        self.assertEqual("rejected", control["evidence_integrity"])
        from showcase.solver_harness.storage import SolverStateStore

        self.assertEqual(parent_before, SolverStateStore(self.connection).get_run("native-fault-parent"))

    def test_multiple_logical_calls_and_http_retries_stay_symmetric(self):
        from showcase.solver_harness.faithful_intervention_native import execute_native_pair

        executor_type = self.prepare_native_pair(
            reservation={"http_attempts": 2, "tool_calls": 0})
        port = self.make_port(attempts_per_call=2)
        report = execute_native_pair(
            self.engine, "native-fault-pair",
            executor=self.executor_for(executor_type, port),
            ledger=self.ledger, job_gate=self.gate,
        )

        self.assertEqual(0, report["evaluable_pairs"], report)
        self.assertEqual(1, report["unknown_pairs"], report)
        self.assertEqual(12, self.ledger.snapshot("native-fault-parent")["http_attempts"])
        self.assertEqual(3, report["arms"]["control"]["cost"]["logical_calls"])
        self.assertEqual(3, report["arms"]["intervention"]["cost"]["logical_calls"])
        self.assertEqual(6, report["arms"]["control"]["cost"]["http_attempts"])
        self.assertEqual(6, report["arms"]["intervention"]["cost"]["http_attempts"])
        self.assertEqual(3, report["budget_reservation"]["logical_calls"] // 2)
        self.assertEqual(report["arms"]["control"]["cost"]["provider_usage"],
                         report["arms"]["intervention"]["cost"]["provider_usage"])


if __name__ == "__main__":
    unittest.main()
