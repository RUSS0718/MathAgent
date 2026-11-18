"""Persistent owner epochs and atomic WorkUnit resource admission."""

import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

from showcase.run_budget import BudgetExhausted, RunBudgetLedger, RunBudgetLimits, bind_budget
from showcase.solver_harness.initial_state import initial_state
from showcase.solver_harness.population_budget import bind_population_action
from showcase.solver_harness.population_store import PopulationConflict, command, initial_population
from showcase.solver_harness.storage import SolverStateStore
from showcase.storage import SQLiteStore

RUN_ID = "population-store-test"
CAPACITY = {
    "service_id": "controlled-http-fixture", "max_inflight": 2,
    "worker_slots": 2, "evidence_ref": "fixture:provider-capacity-v1",
    "status": "controlled",
}
POLICY = {
    "enabled": True, "version": "concurrent-aprs-v1", "schema_version": "population-v1",
    "capacity": CAPACITY, "request_timeout_seconds": 1, "retry_limit": 1,
}


class PopulationStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = str(Path(self.temp.name) / "population.sqlite")
        self.sqlite = SQLiteStore(self.database)
        self.state_store = SolverStateStore(self.sqlite._connection)
        self.ledger = RunBudgetLedger(connection=self.sqlite._connection)
        self.budget = self.ledger.ensure(
            RUN_ID,
            RunBudgetLimits(max_model_calls=3, max_http_attempts=3,
                            max_tokens=100, max_runtime_seconds=20),
        )
        state = initial_state(RUN_ID, "problem", "config", problem_spec={
            "specification_version": 1, "original_problem": "P", "domain": "real",
            "quantifiers": [], "assumptions": [], "directions": [],
            "output_requirements": [],
            "root_obligations": [{"obligation_id": "root:format", "obligation_type": "format",
                                  "statement": "Return the required format"}],
            "auxiliary_goals": [],
        }, proof_graph=True)
        state["progress_policy"] = {"enabled": True, "version": "progress-v1"}
        state["population_policy"] = POLICY
        state["population"] = initial_population()
        state["phase"] = "POPULATION"
        state["plan"] = {"version": 1, "steps": [
            {"step_id": "route-a:step-a", "title": "A", "objective": "A", "depends_on": []},
        ]}
        state["plan_version"] = 1
        state["current_step"] = "route-a:step-a"
        event = {"event_id": "initialized", "run_id": RUN_ID, "type": "run_initialized",
                 "state_revision": 0, "created_at": state["created_at"]}
        self.state_store.create_run(state, event)
        self.harness = SimpleNamespace(
            _state_store=self.state_store, _showcase_store=self.sqlite,
            _population_owner=None, _event_observer=None,
        )
        self.run = self.state_store.get_run(RUN_ID)
        self.run = command(self.harness, RUN_ID, "claim", owner_id="owner-1")
        self.harness._population_owner = self.run["state"]["population"]["owner"]
        self.run = command(self.harness, RUN_ID, "patch", updates={
            "closing_reserve": {"model_calls": 1, "http_attempts": 1,
                                "tokens": 20, "time_seconds": 1, "tool_calls": 0},
        })
        route_state = dict(self.run["state"])
        route_state.update(plan_version=11, state_revision=0, current_step="route-a:step-a")
        self.run = command(
            self.harness, RUN_ID, "register_route", route_id="route-a",
            frontier_digest="frontier-a", snapshot=route_state,
        )

    def tearDown(self):
        self.sqlite.close()

    def _admit(self):
        return command(
            self.harness, RUN_ID, "admit", route_id="route-a", action_id="action-a",
            reservation={"calls": [{"role": "reasoner", "input_estimate": 20,
                                     "output_cap": 10, "http_attempts": 1}],
                         "model_calls": 1, "http_attempts": 1, "tokens": 30,
                         "tool_calls": 0, "time_seconds": 2},
            closing_reserve={"model_calls": 1, "http_attempts": 1,
                             "tokens": 20, "time_seconds": 1, "tool_calls": 0},
            dependencies=[],
        )

    def test_identical_rating_in_consecutive_rounds_retains_both_rounds(self):
        from showcase.solver_harness.population_schedule import round_schedule

        first = round_schedule(self.run["state"]["population"])
        run = command(self.harness, RUN_ID, "patch", updates=first)
        next_population = dict(run["state"]["population"])
        next_population["opportunities"] = list(first["round_members"])
        second = round_schedule(next_population)
        self.assertEqual(first["rating"], second["rating"])
        run = command(self.harness, RUN_ID, "patch", updates=second)
        history = run["state"]["population"]["rating_history"]
        self.assertEqual([1, 2], [entry["round"] for entry in history])

    def test_independent_process_takeover_fences_previous_dispatch_owner(self):
        script = """
import sys
from types import SimpleNamespace
from showcase.storage import SQLiteStore
from showcase.solver_harness.storage import SolverStateStore
from showcase.solver_harness.population_store import command
with SQLiteStore(sys.argv[1]) as store:
    harness = SimpleNamespace(_state_store=SolverStateStore(store._connection),
        _showcase_store=store, _population_owner=None, _event_observer=None)
    run = command(harness, sys.argv[2], 'claim', owner_id='process-owner', takeover=True)
    print(run['state']['population']['epoch'])
"""
        child = subprocess.run([sys.executable, "-c", script, self.database, RUN_ID],
                               capture_output=True, text=True, timeout=15)
        self.assertEqual(0, child.returncode, child.stderr)
        self.assertEqual("2", child.stdout.strip())
        with self.assertRaisesRegex(PopulationConflict, "population_owner_epoch_mismatch"):
            self._admit()
        state = self.state_store.get_run(RUN_ID)["state"]
        self.assertEqual({}, state["population"]["actions"])

    def test_takeover_fences_old_owner_finalization_requests(self):
        previous = dict(self.harness._population_owner)
        command(self.harness, RUN_ID, "claim", owner_id="new-final-owner", takeover=True)
        with bind_budget(self.budget), bind_population_action(None, previous):
            with self.assertRaisesRegex(BudgetExhausted, "population_owner_epoch_mismatch"):
                self.budget.model_call("final_generator", solver_call_id="stale-final")

    def test_answer_freeze_blocks_reserved_worker_from_starting_another_call(self):
        self._admit()
        command(self.harness, RUN_ID, "freeze", candidate={"text_hash": "frozen"})
        with bind_budget(self.budget), bind_population_action(
            "action-a", self.harness._population_owner
        ):
            with self.assertRaisesRegex(BudgetExhausted, "population_exploration_frozen"):
                self.budget.model_call("reasoner", solver_call_id="after-freeze")

    def test_admission_reserves_provider_request_before_dispatch_and_reuses_its_slots(self):
        self.run = self._admit()
        summary = self.budget.snapshot()
        self.assertEqual((1, 1, 30), (
            summary["logical_calls"], summary["http_attempts"], summary["charged_tokens"],
        ))
        with bind_budget(self.budget), bind_population_action(
            "action-a", self.harness._population_owner
        ):
            call = self.budget.model_call("reasoner", solver_call_id="solver-call")
            timeout = call.before_attempt({
                "attempt_id": "http-attempt", "solver_call_id": "solver-call",
                "started_at_utc": "2026-11-09T00:00:00+00:00", "role": "reasoner",
                "max_tokens": 10,
            }, 15)
            self.assertGreater(timeout, 0)
            with self.assertRaises(BudgetExhausted):
                self.budget.model_call("reasoner", solver_call_id="second-call")
            call.after_attempt({"attempt_id": "http-attempt", "status": "success",
                                "prompt_tokens": 5, "completion_tokens": 6,
                                "total_tokens": 11})
        saved = self.state_store.get_run(RUN_ID)
        self.assertEqual("inflight", saved["state"]["population"]["actions"]["action-a"]["status"])
        self.assertEqual(1, self.budget.snapshot()["logical_calls"])

    def test_stale_owner_cannot_write_math_but_can_settle_physical_outcome(self):
        self.run = self._admit()
        old_owner = self.harness._population_owner
        replacement = SimpleNamespace(**self.harness.__dict__)
        replacement._population_owner = None
        self.run = command(replacement, RUN_ID, "claim", owner_id="owner-2", takeover=True)
        replacement._population_owner = self.run["state"]["population"]["owner"]
        with self.assertRaises(PopulationConflict):
            command(self.harness, RUN_ID, "route_commit", route_id="route-a", action_id="action-a",
                    expected_route_revision=0,
                    event={"event_id": "late-proof", "type": "step_reviewed", "verdict": "ACCEPT"},
                    updates={"verified_results_ledger": [{"result_id": "forged"}]})
        self.harness._population_owner = old_owner
        self.run = command(self.harness, RUN_ID, "outcome", action_id="action-a", status="completed")
        self.harness._population_owner = replacement._population_owner
        with self.assertRaises(PopulationConflict):
            command(self.harness, RUN_ID, "accept", action_id="action-a")
        action = self.run["state"]["population"]["actions"]["action-a"]
        self.assertFalse(action["accepted"])
        self.assertEqual("unknown", action["status"])
        self.assertEqual("unknown", self.run["state"]["population"]["routes"]["route-a"]["status"])

    def test_timeout_error_keeps_unknown_physical_capacity_and_budget_hold(self):
        self._admit()
        with bind_budget(self.budget), bind_population_action("action-a", self.harness._population_owner):
            call = self.budget.model_call("reasoner", solver_call_id="timed-out")
            call.before_attempt({"attempt_id": "timeout-http", "role": "reasoner", "max_tokens": 10}, 15)
            call.after_attempt({"attempt_id": "timeout-http", "status": "error", "error_category": "timeout"})
        run = command(self.harness, RUN_ID, "outcome", action_id="action-a", status="unknown")
        self.assertEqual("pending", run["state"]["population"]["actions"]["action-a"]["settlement_status"])
        self.assertEqual(30, self.budget.snapshot()["reserved_tokens"])

    def test_unknown_action_keeps_its_reservation_and_capacity_until_settled(self):
        self.run = self._admit()
        self.run = command(self.harness, RUN_ID, "outcome", action_id="action-a", status="unknown")
        action = self.run["state"]["population"]["actions"]["action-a"]
        self.assertEqual("unknown", action["status"])
        self.assertEqual(1, self.run["state"]["population"]["settlement"]["unknown_count"])
        self.assertEqual(30, self.budget.snapshot()["charged_tokens"])
        self.assertEqual("unknown", self.run["state"]["population"]["routes"]["route-a"]["status"])

    def test_late_http_success_settles_resources_without_accepting_route_math(self):
        self.run = self._admit()
        event = {
            "attempt_id": "attempt-late", "solver_call_id": "solver-call",
            "started_at_utc": "2026-11-09T00:00:00+00:00", "role": "reasoner",
            "max_tokens": 10,
        }
        with bind_budget(self.budget), bind_population_action(
            "action-a", self.harness._population_owner
        ):
            call = self.budget.model_call("reasoner", solver_call_id="solver-call")
            call.before_attempt(event, 15)
            call.after_attempt({"attempt_id": "attempt-late", "status": "unknown"})
        self.run = command(self.harness, RUN_ID, "outcome", action_id="action-a", status="unknown")
        action_before = self.run["state"]["population"]["actions"]["action-a"]
        self.assertEqual("pending", action_before["settlement_status"])
        self.assertEqual(30, self.budget.snapshot()["charged_tokens"])

        self.ledger.settle(RUN_ID, "attempt-late", {
            "attempt_id": "attempt-late", "status": "success",
            "prompt_tokens": 5, "completion_tokens": 6, "total_tokens": 11,
        })
        settled = self.state_store.get_run(RUN_ID)
        action_after = settled["state"]["population"]["actions"]["action-a"]
        self.assertEqual("unknown", action_after["status"])
        self.assertEqual("settled", action_after["settlement_status"])
        self.assertEqual("settled", settled["state"]["population"]["settlement"]["status"])
        self.assertEqual("unknown", settled["state"]["population"]["routes"]["route-a"]["status"])
        self.assertEqual(0, self.budget.snapshot()["reserved_tokens"])
        self.assertEqual(11, self.budget.snapshot()["charged_tokens"])

    def test_snapshot_reconciliation_never_waits_for_in_process_math_lock(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event, Thread

        from showcase.solver_harness.population_settlement import reconcile_database
        from showcase.solver_harness.storage import _SOLVER_STORAGE_LOCK

        self._admit()
        with bind_budget(self.budget), bind_population_action("action-a", self.harness._population_owner):
            call = self.budget.model_call("reasoner", solver_call_id="pending-read")
            call.before_attempt({"attempt_id": "pending-read-http", "max_tokens": 10}, 15)
        command(self.harness, RUN_ID, "outcome", action_id="action-a", status="unknown")
        acquired, release = Event(), Event()
        def hold_lock():
            with _SOLVER_STORAGE_LOCK:
                acquired.set()
                release.wait(5)
        thread = Thread(target=hold_lock)
        thread.start()
        self.assertTrue(acquired.wait(2))
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(reconcile_database, self.database, RUN_ID)
            try:
                future.result(timeout=0.5)
            finally:
                release.set()
                thread.join(2)

    def test_read_reconciles_committed_usage_after_population_callback_was_lost(self):
        from unittest.mock import patch

        from showcase.star_product_projection import persisted_solver

        self._admit()
        with bind_budget(self.budget), bind_population_action("action-a", self.harness._population_owner):
            call = self.budget.model_call("reasoner", solver_call_id="lost-callback")
            call.before_attempt({"attempt_id": "lost-http", "max_tokens": 10, "role": "reasoner"}, 15)
            call.after_attempt({"attempt_id": "lost-http", "status": "unknown"})
        command(self.harness, RUN_ID, "outcome", action_id="action-a", status="unknown")
        with patch.object(self.ledger, "_settle_population_resource"):
            self.ledger.settle(RUN_ID, "lost-http", {"status": "success", "prompt_tokens": 2,
                              "completion_tokens": 3, "total_tokens": 5})
        before = self.state_store.get_run(RUN_ID)["state"]["population"]
        self.assertEqual("pending", before["settlement"]["status"])
        projected, _ = persisted_solver(self.sqlite._connection, RUN_ID)
        self.assertEqual("settled", projected["state"]["population"]["settlement"]["status"])
        self.assertEqual("unknown", projected["state"]["population"]["actions"]["action-a"]["status"])
        again, _ = persisted_solver(self.sqlite._connection, RUN_ID)
        self.assertEqual(projected["state_revision"], again["state_revision"])

    def test_explicit_retry_creates_new_action_and_retains_the_unknown_identity(self):
        self.run = self._admit()
        old_call = {
            "call_id": "call-unknown", "role": "reasoner", "status": "unknown_outcome",
            "request_revision": 1, "request": {"role": "reasoner"},
            "request_hash": "request-hash", "action_id": "action-a",
        }
        self.run = command(
            self.harness, RUN_ID, "route_commit", route_id="route-a", action_id="action-a",
            expected_route_revision=0,
            event={"event_id": "call-unknown", "type": "call_audit", "outcome": "unknown_outcome"},
            updates={"calls": {"call-unknown": old_call}},
        )
        self.run = command(self.harness, RUN_ID, "outcome", action_id="action-a", status="unknown")
        new_call_id = str(uuid.uuid4())

        self.run = command(self.harness, RUN_ID, "retry", retry_call={
            "call_id": "call-unknown", "new_call_id": new_call_id,
        })
        population = self.run["state"]["population"]
        route = population["routes"]["route-a"]
        self.assertEqual("eligible", route["status"])
        self.assertIsNone(route["inflight_action_id"])
        self.assertEqual("call-unknown", route["snapshot"]["authorized_retry"]["call_id"])
        self.assertEqual("unknown", population["actions"]["action-a"]["status"])
        self.assertEqual(30, self.budget.snapshot()["charged_tokens"])

        self.run = command(
            self.harness, RUN_ID, "admit", route_id="route-a", action_id="action-retry",
            reservation={"calls": [{"role": "reasoner", "input_estimate": 20,
                                     "output_cap": 10, "http_attempts": 1}],
                        "model_calls": 1, "http_attempts": 1, "tokens": 30,
                        "tool_calls": 0, "time_seconds": 2},
            closing_reserve={"model_calls": 1, "http_attempts": 1,
                             "tokens": 20, "time_seconds": 1, "tool_calls": 0},
            dependencies=[],
        )
        population = self.run["state"]["population"]
        self.assertEqual("unknown", population["actions"]["action-a"]["status"])
        self.assertEqual("inflight", population["actions"]["action-retry"]["status"])
        self.assertEqual("action-retry", population["routes"]["route-a"]["inflight_action_id"])


if __name__ == "__main__":
    unittest.main()
