"""Durable registrations and same-checkpoint intervention experiments."""

from __future__ import annotations

import hashlib
import json
import random
import sqlite3
import threading
from collections.abc import Callable, Mapping
from dataclasses import asdict
from typing import Any

from .faithful_intervention_budget import reserve_pair_budget
from .faithful_intervention_records import (
    FailureHypothesis,
    FaithfulInterventionError,
    ParentJobGate,
    ProofAction,
    _encode,
    _normalize_action,
    _normalize_hypothesis,
    _normalize_reservation,
    _required_text,
    _single_parameter_difference,
)
from .storage import SolverStateStore


class FaithfulInterventionEngine:
    """Persist registrations and symmetric pair reservations on an existing Run.

    The engine owns sidecar hypothesis, action, and pair records on the existing
    Showcase SQLite connection. Solver state and resource accounting remain owned
    by SolverStateStore and RunBudgetLedger. Execution requires an explicit executor.
    """

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        connection_lock=None,
        initialize_schema: bool = True,
    ) -> None:
        self._connection = connection
        self._lock = connection_lock or threading.RLock()
        if not initialize_schema:
            return
        statements = (
            "CREATE TABLE IF NOT EXISTS faithful_intervention_hypotheses "
            "(hypothesis_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS faithful_intervention_actions "
            "(action_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS faithful_intervention_pairs "
            "(pair_id TEXT PRIMARY KEY, identity_hash TEXT NOT NULL, "
            "checkpoint_json TEXT NOT NULL, report_json TEXT NOT NULL)",
        )
        with self._lock:
            for statement in statements:
                connection.execute(statement)

    def register_hypothesis(
        self,
        hypothesis: FailureHypothesis,
        *,
        transaction_hook: Callable[[sqlite3.Connection], None] | None = None,
    ) -> FailureHypothesis:
        value = _normalize_hypothesis(hypothesis)
        self._register(
            "faithful_intervention_hypotheses", "hypothesis_id", value.hypothesis_id,
            _encode(asdict(value)), transaction_hook,
        )
        return value

    def register_action(
        self,
        action: ProofAction,
        *,
        transaction_hook: Callable[[sqlite3.Connection], None] | None = None,
    ) -> ProofAction:
        value = _normalize_action(action)
        self._register(
            "faithful_intervention_actions", "action_id", value.action_id,
            _encode(asdict(value)), transaction_hook,
        )
        return value

    def get_hypothesis(self, hypothesis_id: str) -> FailureHypothesis:
        row = self._connection.execute(
            "SELECT payload_json FROM faithful_intervention_hypotheses WHERE hypothesis_id=?",
            (hypothesis_id,),
        ).fetchone()
        if row is None:
            raise KeyError("hypothesis_not_found")
        return _normalize_hypothesis(json.loads(row[0]))

    def get_action(self, action_id: str) -> ProofAction:
        row = self._connection.execute(
            "SELECT payload_json FROM faithful_intervention_actions WHERE action_id=?",
            (action_id,),
        ).fetchone()
        if row is None:
            raise KeyError("action_not_found")
        return _normalize_action(json.loads(row[0]))

    def reserve_pair(
        self,
        *,
        job_id: str,
        job_gate: ParentJobGate,
        run_id: str,
        expected_revision: int,
        hypothesis_id: str,
        control_action_id: str,
        intervention_action_id: str,
        pair_id: str,
        seed: int,
        reservation: Mapping[str, Any],
        transaction_hook: Callable[[sqlite3.Connection], None] | None = None,
    ) -> Mapping[str, Any]:
        """Freeze one committed checkpoint and reserve equal Run-budget holds.

        No branch is dispatched here. The caller's Job gate is checked inside
        the same SQLite transaction as both reservations and the optional action hook.
        """
        for value, reason in ((job_id, "job_id_required"), (run_id, "run_id_required"),
                              (hypothesis_id, "hypothesis_id_required"),
                              (control_action_id, "control_action_id_required"),
                              (intervention_action_id, "intervention_action_id_required"),
                              (pair_id, "pair_id_required")):
            _required_text(value, reason)
        if type(expected_revision) is not int or expected_revision < 0:
            raise FaithfulInterventionError("checkpoint_revision_invalid")
        if type(seed) is not int or seed < 0:
            raise FaithfulInterventionError("pair_seed_invalid")
        if not callable(getattr(job_gate, "assert_paused", None)):
            raise FaithfulInterventionError("parent_job_gate_required")
        calls = _normalize_reservation(reservation)
        hypothesis = self.get_hypothesis(hypothesis_id)
        control = self.get_action(control_action_id)
        intervention = self.get_action(intervention_action_id)
        if not {control_action_id, intervention_action_id}.issubset(
            hypothesis.candidate_action_ids
        ):
            raise FaithfulInterventionError("action_not_registered_for_hypothesis")
        if not _single_parameter_difference(control, intervention):
            raise FaithfulInterventionError("single_action_difference_required")

        snapshot = SolverStateStore(self._connection).get_run(run_id)
        if snapshot is None:
            raise FaithfulInterventionError("parent_solver_run_not_found")
        state = snapshot["state"]
        if snapshot["state_revision"] != expected_revision:
            raise FaithfulInterventionError("checkpoint_revision_conflict")
        if state.get("phase") == "TERMINAL":
            raise FaithfulInterventionError("parent_run_terminal")
        parent_state = state
        if state.get("serial_checkpoint"):
            from .autonomous_routes import serial_checkpoint_view

            state = serial_checkpoint_view(state, expected_revision=expected_revision)
        checkpoint = {
            "run_id": run_id,
            "state_revision": expected_revision,
            "problem_hash": state["problem_hash"],
            "config_hash": state["config_hash"],
            "state": state,
        }
        budget_row = self._connection.execute(
            "SELECT ledger_json FROM run_budgets WHERE run_id=?", (run_id,)).fetchone()
        prior = self._connection.execute(
            "SELECT checkpoint_json FROM faithful_intervention_pairs WHERE pair_id=?", (pair_id,)).fetchone()
        frozen = json.loads(prior[0]) if prior else None
        if frozen is not None and all(frozen.get(key) == value for key, value in checkpoint.items()):
            checkpoint = frozen
        else:
            checkpoint["budget_checkpoint"] = json.loads(budget_row[0]) if budget_row else None
        checkpoint_json = _encode(checkpoint)
        checkpoint_hash = hashlib.sha256(checkpoint_json.encode("utf-8")).hexdigest()
        order = ["control", "intervention"]
        random.Random(seed).shuffle(order)
        identity = {
            "job_id": job_id,
            "run_id": run_id,
            "checkpoint_hash": checkpoint_hash,
            "hypothesis_id": hypothesis_id,
            "control_action_id": control_action_id,
            "intervention_action_id": intervention_action_id,
            "seed": seed,
            "reservation": calls,
        }
        identity_hash = hashlib.sha256(_encode(identity).encode("utf-8")).hexdigest()
        branch_ids = {arm: f"{pair_id}:{arm}" for arm in ("control", "intervention")}
        report = {
            "pair_id": pair_id,
            "job_id": job_id,
            "run_id": run_id,
            "checkpoint_revision": expected_revision,
            "checkpoint_hash": checkpoint_hash,
            "hypothesis_id": hypothesis_id,
            "seed": seed,
            "order": order,
            "status": "reserved",
            "started_pairs": 0,
            "denominator": 0,
            "evaluable_pairs": 0,
            "incomplete_pairs": 0,
            "unknown_pairs": 0,
            "effect": None,
            "budget_reservation": None,
            "arms": {
                "control": {"branch_id": branch_ids["control"], "action_id": control_action_id,
                            "status": "not_started"},
                "intervention": {
                    "branch_id": branch_ids["intervention"],
                    "action_id": intervention_action_id, "status": "not_started",
                },
            },
        }
        connection = self._connection
        with self._lock:
            if connection.in_transaction:
                raise FaithfulInterventionError("pair_transaction_already_open")
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    "SELECT identity_hash,report_json FROM faithful_intervention_pairs WHERE pair_id=?",
                    (pair_id,),
                ).fetchone()
                if existing is not None:
                    if existing[0] != identity_hash:
                        raise FaithfulInterventionError("pair_identity_conflict")
                    if transaction_hook is not None:
                        transaction_hook(connection)
                    connection.commit()
                    return json.loads(existing[1])
                current = connection.execute(
                    "SELECT state_json,problem_hash,config_hash,state_revision "
                    "FROM solver_states WHERE run_id=?", (run_id,),
                ).fetchone()
                if (current is None or current[3] != expected_revision
                        or current[0] != _encode(parent_state)
                        or current[1] != state["problem_hash"]
                        or current[2] != state["config_hash"]):
                    raise FaithfulInterventionError("checkpoint_revision_conflict")
                current_budget = connection.execute(
                    "SELECT ledger_json FROM run_budgets WHERE run_id=?", (run_id,)).fetchone()
                if (current_budget is not None and
                        json.loads(current_budget[0]) != checkpoint["budget_checkpoint"]):
                    raise FaithfulInterventionError("checkpoint_budget_conflict")
                job_gate.assert_paused(
                    connection=connection, job_id=job_id, run_id=run_id,
                    checkpoint_revision=expected_revision,
                )
                report["budget_reservation"] = reserve_pair_budget(
                    connection, run_id, pair_id, calls
                )
                connection.execute(
                    "INSERT INTO faithful_intervention_pairs "
                    "(pair_id,identity_hash,checkpoint_json,report_json) VALUES (?,?,?,?)",
                    (pair_id, identity_hash, checkpoint_json, _encode(report)),
                )
                if transaction_hook is not None:
                    transaction_hook(connection)
                connection.commit()
                return report
            except BaseException:
                connection.rollback()
                raise

    def get_pair(self, pair_id: str) -> Mapping[str, Any]:
        row = self._connection.execute(
            "SELECT report_json FROM faithful_intervention_pairs WHERE pair_id=?", (pair_id,)
        ).fetchone()
        if row is None:
            raise KeyError("pair_not_found")
        from .faithful_intervention_effects import recheck_native_report
        from .faithful_intervention_execution import project_report

        report = project_report(recheck_native_report(self._connection, json.loads(row[0])))
        from .faithful_intervention_budget import arm_budget_snapshot

        if report["started_pairs"]:
            for arm in ("control", "intervention"):
                report["arms"][arm]["cost"] = arm_budget_snapshot(
                    self._connection, report["run_id"], pair_id, arm
                )
        return report

    def execute_pair(self, pair_id: str, *, execute_branch, ledger, job_gate):
        """Execute exactly one registered action per arm; never create complete Solver Runs."""
        from .faithful_intervention_execution import execute_pair

        return execute_pair(self, pair_id, execute_branch=execute_branch,
                            ledger=ledger, job_gate=job_gate)

    def _register(self, table, key_column, key, payload, transaction_hook):
        connection = self._connection
        with self._lock:
            if connection.in_transaction:
                raise FaithfulInterventionError("registration_transaction_already_open")
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    f"SELECT payload_json FROM {table} WHERE {key_column}=?", (key,)
                ).fetchone()
                if row is not None:
                    if row[0] != payload:
                        raise FaithfulInterventionError("registration_identity_conflict")
                else:
                    connection.execute(
                        f"INSERT INTO {table}({key_column},payload_json) VALUES (?,?)",
                        (key, payload),
                    )
                if transaction_hook is not None:
                    transaction_hook(connection)
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
