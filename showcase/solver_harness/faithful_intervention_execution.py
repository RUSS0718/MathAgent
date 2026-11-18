"""Single-action pair execution; caller supplies real executor and parent Job gate."""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import time
from copy import deepcopy
from datetime import UTC, datetime

from ..redaction import redact
from ..run_budget import BudgetExhausted, ModelCallBudget, RunBudget, bind_budget
from .faithful_intervention_budget import arm_budget_snapshot, release_unused_arm_holds
from .faithful_intervention_records import BranchOutcome, FaithfulInterventionError, _encode

_ACTIVE_PAIRS: set[str] = set()
_ACTIVE_PAIRS_LOCK = threading.Lock()


class ArmBudget(RunBudget):
    """Use only this arm's pre-reserved logical slots on the parent ledger."""

    def __init__(self, ledger, run_id, role):
        super().__init__(ledger, run_id)
        self.role = role

    def model_call(self, role=None, *, solver_call_id=None, deadline_at=None,
                   strict_completion=False):
        if time.time() >= self.absolute_deadline():
            raise BudgetExhausted("intervention_arm_budget_exhausted")
        native_claim = getattr(self.ledger, "claim_native_call", None)
        logical_id = (native_claim(self.run_id, role, solver_call_id=solver_call_id)
                      if callable(native_claim) else self.ledger.claim_finalization_call(
                          self.run_id, self.role, solver_call_id=solver_call_id))
        if logical_id is None:
            raise BudgetExhausted("intervention_arm_reservation_missing")
        call = ArmCallBudget(self.ledger, self.run_id, logical_id, self.role,
                             solver_call_id, min(deadline_at or self.absolute_deadline(),
                                                 self.absolute_deadline()), strict_completion)
        call.max_attempts = getattr(self.ledger, "attempts_per_call", 1)
        return call


class ArmCallBudget(ModelCallBudget):
    """Consume only the physical attempt count reserved for this logical call."""

    def before_attempt(self, event, input_estimate):
        attempted = getattr(self, "attempt_ids", set())
        if len(attempted) >= getattr(self, "max_attempts", 1):
            raise BudgetExhausted("intervention_attempt_reservation_exhausted")
        result = super().before_attempt(event, input_estimate)
        self.attempt_ids = attempted | {event["attempt_id"]}
        return result

    def after_attempt(self, event):
        if event.get("attempt_id") not in getattr(self, "attempt_ids", set()):
            raise FaithfulInterventionError("intervention_cross_arm_settlement")
        return super().after_attempt(event)


def execute_pair(engine, pair_id, *, execute_branch, ledger, job_gate, budget_factory=None):
    """Track the live owner so explicit recovery cannot abandon active work."""
    with _ACTIVE_PAIRS_LOCK:
        if pair_id in _ACTIVE_PAIRS:
            raise FaithfulInterventionError("intervention_pair_execution_active")
        _ACTIVE_PAIRS.add(pair_id)
    try:
        return _execute_pair(engine, pair_id, execute_branch=execute_branch, ledger=ledger,
                             job_gate=job_gate, budget_factory=budget_factory)
    finally:
        with _ACTIVE_PAIRS_LOCK:
            _ACTIVE_PAIRS.discard(pair_id)


def _execute_pair(engine, pair_id, *, execute_branch, ledger, job_gate, budget_factory=None):
    if not callable(execute_branch):
        raise FaithfulInterventionError("branch_executor_required")
    if ledger.connection is not engine._connection:
        raise FaithfulInterventionError("parent_ledger_connection_mismatch")
    connection = engine._connection
    with engine._lock:
        if connection.in_transaction:
            raise FaithfulInterventionError("pair_transaction_already_open")
        connection.execute("BEGIN IMMEDIATE")
        try:
            row = connection.execute(
                "SELECT checkpoint_json,report_json FROM faithful_intervention_pairs WHERE pair_id=?",
                (pair_id,),
            ).fetchone()
            if row is None:
                raise KeyError("pair_not_found")
            checkpoint, report = json.loads(row[0]), json.loads(row[1])
            if report["status"] != "reserved":
                connection.commit()
                return project_report(report)
            _check_parent(engine, report, checkpoint, job_gate)
            if time.time() >= report["budget_reservation"]["deadline_at"]:
                raise BudgetExhausted("run_deadline_exhausted")
            report.update(status="running", started_pairs=1, denominator=1)
            _write(connection, report)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise

    for arm in report["order"]:
        started = time.monotonic()
        with engine._lock:
            _check_parent(engine, report, checkpoint, job_gate)
            report["arms"][arm]["status"] = "dispatching"
            _save(engine, report)
        record = report["arms"][arm]
        role = report["budget_reservation"]["arm_roles"][arm]
        budget = (budget_factory(ledger, report, arm, job_gate) if budget_factory is not None
                  else ArmBudget(ledger, report["run_id"], role))
        record["started_at_utc"] = datetime.now(UTC).isoformat()
        record["arm_deadline_at"] = budget.absolute_deadline()
        _save(engine, report)
        outcome = None
        try:
            with bind_budget(budget):
                outcome = execute_branch(
                    checkpoint=deepcopy(checkpoint),
                    action=engine.get_action(record["action_id"]),
                    branch_id=record["branch_id"], arm=arm,
                    budget=budget, budget_role=role,
                )
            if not isinstance(outcome, BranchOutcome):
                raise FaithfulInterventionError("branch_outcome_required")
            if outcome.status not in {"completed", "failed", "incomplete", "unknown_outcome"}:
                raise FaithfulInterventionError("branch_outcome_status_invalid")
            if outcome.measurement is not None and (
                type(outcome.measurement) not in {int, float}
                or not math.isfinite(outcome.measurement)
            ):
                raise FaithfulInterventionError("branch_measurement_invalid")
            # JSON serialization validates evidence before writing the receipt.
            _encode({"evidence": outcome.evidence, "events": outcome.events})
        except (BudgetExhausted, FaithfulInterventionError):
            outcome = BranchOutcome("incomplete")
            record["failure"] = "admission_rejected; details excluded"
        except Exception:
            outcome = BranchOutcome("unknown_outcome")
            record["failure"] = "executor_failed; details excluded"
        with engine._lock:
            cost = arm_budget_snapshot(connection, report["run_id"], pair_id, arm)
            # No callback assertion can turn absent/unsettled physical evidence into success.
            status = outcome.status
            if cost["unknown_attempts"] or cost.get("unknown_tool_calls"):
                status = "unknown_outcome"
            elif status != "unknown_outcome" and (
                not cost["http_attempts"] or not cost["logical_calls"]
            ):
                status = "incomplete"
            elif status != "unknown_outcome" and time.time() >= budget.absolute_deadline():
                status = "incomplete"
            record.update(
                status=status, cost=cost, duration_seconds=time.monotonic() - started,
                measurement=outcome.measurement if status == "completed" else None,
                evidence=redact(outcome.evidence),
                events=[{**dict(event), "branch_id": record["branch_id"], "arm": arm,
                         "run_id": report["run_id"], "pair_id": pair_id}
                        for event in redact(outcome.events)],
            )
            # Inflight/unknown requests retain their original holds for late settlement.
            record["released_unused_holds"] = release_unused_arm_holds(
                connection, report["run_id"], pair_id, arm)
            _save(engine, report)

    report = project_report(report)
    report["status"] = "completed" if report["evaluable_pairs"] else "incomplete"
    report["branch_engine"] = "external_adapter"
    report["parent_resume"] = "unavailable"
    with engine._lock:
        _check_parent(engine, report, checkpoint, job_gate)
        _save(engine, report)
    return report


def abandon_interrupted_pair(engine, pair_id, *, ledger, job_gate):
    """Persist an explicit, non-replaying resolution of a dead pair executor."""
    if ledger.connection is not engine._connection:
        raise FaithfulInterventionError("parent_ledger_connection_mismatch")
    connection = engine._connection
    with _ACTIVE_PAIRS_LOCK:
        if pair_id in _ACTIVE_PAIRS:
            raise FaithfulInterventionError("intervention_pair_execution_active")
        with engine._lock:
            if connection.in_transaction:
                raise FaithfulInterventionError("pair_transaction_already_open")
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT checkpoint_json,report_json FROM faithful_intervention_pairs WHERE pair_id=?",
                    (pair_id,),
                ).fetchone()
                if row is None:
                    raise KeyError("pair_not_found")
                checkpoint, report = json.loads(row[0]), json.loads(row[1])
                if report["status"] == "interrupted":
                    connection.commit()
                    return project_report(report)
                if report["status"] != "running" or not report["started_pairs"]:
                    raise FaithfulInterventionError("intervention_pair_not_interrupted")
                _check_parent(engine, report, checkpoint, job_gate)
                _assert_no_live_owner(connection, pair_id)

                for arm, record in report["arms"].items():
                    if record["status"] == "dispatching":
                        record["status"] = "unknown_outcome"
                        record["duration_seconds"] = _elapsed_seconds(record.get("started_at_utc"))
                    elif record["status"] == "not_started":
                        record["duration_seconds"] = 0.0
                    release_unused_arm_holds(connection, report["run_id"], pair_id, arm)
                    record["cost"] = arm_budget_snapshot(connection, report["run_id"], pair_id, arm)

                report.update(
                    status="interrupted",
                    denominator=1,
                    interruption="explicitly_abandoned",
                    parent_resume="checkpoint_preserved",
                    effect=None,
                )
                _write(connection, report)
                _save_resources(connection, report)
                if _has_pair_owner_table(connection):
                    connection.execute(
                        "UPDATE faithful_intervention_pair_owners "
                        "SET execution_status='interrupted',updated_at=? WHERE pair_id=?",
                        (time.time(), pair_id),
                    )
                result = project_report(report)
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise


def project_report(report):
    report = deepcopy(report)
    if not report["started_pairs"]:
        return report
    statuses = []
    for arm in report["arms"].values():
        if arm["status"] == "dispatching":
            arm["status"] = "unknown_outcome"
        statuses.append(arm["status"])
    report["denominator"] = 1
    report["unknown_pairs"] = int("unknown_outcome" in statuses)
    measurements = [report["arms"][arm].get("measurement")
                    for arm in ("control", "intervention")]
    evaluable = all(status == "completed" for status in statuses) and all(
        value is not None for value in measurements)
    report["evaluable_pairs"] = int(evaluable)
    report["incomplete_pairs"] = int(not evaluable and not report["unknown_pairs"])
    report["effect"] = ({"method": "single_pair_descriptive_difference",
                         "sample_size": 1,
                         "measurement_delta": measurements[1] - measurements[0],
                         "interval": None, "interval_reason": "sample_size_one",
                         "policy_updated": False} if evaluable else None)
    suggested = None
    if evaluable and report.get("branch_engine") == "native_solver_checkpoint":
        if measurements[1] > measurements[0]:
            suggested = report["arms"]["intervention"]["action_id"]
        elif measurements[0] > measurements[1]:
            suggested = report["arms"]["control"]["action_id"]
    report["feedback"] = {
        "version": "faithful-effect-feedback-v1", "source_pair_id": report["pair_id"],
        "source_checkpoint_hash": report["checkpoint_hash"],
        "source_policy_version": report.get("policy_version"),
        "suggested_action_id": suggested,
        "status": "descriptive_only_parent_recheck_required" if evaluable else "not_evaluable",
        "policy_updated": False, "mathematical_evidence_merged": False,
    }
    if report["status"] == "running":
        report["status"] = "incomplete"
    return report


def _check_parent(engine, report, checkpoint, gate):
    row = engine._connection.execute(
        "SELECT state_json,state_revision FROM solver_states WHERE run_id=?",
        (report["run_id"],),
    ).fetchone()
    if row is None or row[1] != report["checkpoint_revision"]:
        raise FaithfulInterventionError("checkpoint_revision_conflict")
    state = json.loads(row[0])
    if checkpoint["state"].get("serial_checkpoint_source"):
        from .autonomous_routes import serial_checkpoint_view

        state = serial_checkpoint_view(state, expected_revision=row[1])
    actual = {**checkpoint, "state": state}
    digest = hashlib.sha256(_encode(actual).encode("utf-8")).hexdigest()
    if digest != report["checkpoint_hash"]:
        raise FaithfulInterventionError("checkpoint_drift")
    gate.assert_paused(connection=engine._connection, job_id=report["job_id"],
                       run_id=report["run_id"], checkpoint_revision=report["checkpoint_revision"])


def _write(connection, report):
    connection.execute(
        "UPDATE faithful_intervention_pairs SET report_json=? WHERE pair_id=?",
        (_encode(report), report["pair_id"]),
    )


def _save(engine, report):
    with engine._lock:
        with engine._connection:
            _write(engine._connection, report)
            _save_resources(engine._connection, report)


def _save_resources(connection, report):
    row = connection.execute(
        "SELECT ledger_json FROM run_budgets WHERE run_id=?", (report["run_id"],)).fetchone()
    if row is None or not report.get("started_pairs"):
        return
    ledger = json.loads(row[0])
    arms = list(report["arms"].values())
    unknown = any(item.get("status") in {"dispatching", "unknown_outcome"}
                  or item.get("cost", {}).get("unknown_attempts")
                  or item.get("cost", {}).get("unknown_tool_calls") for item in arms)
    dispatched = any(item.get("status") != "not_started" for item in arms)
    elapsed = [item.get("duration_seconds") for item in arms if item.get("duration_seconds") is not None]
    all_durations_known = len(elapsed) == len(arms)
    ledger.setdefault("intervention_resources", {})[report["pair_id"]] = {
        "local_peak_admitted_arms": int(dispatched),
        "remote_peak_concurrency": None if unknown else int(any(
            item.get("cost", {}).get("http_attempts", 0) for item in arms)),
        "unknown_remote_concurrency": unknown,
        "arm_wall_time_seconds": sum(elapsed) if all_durations_known else None,
        "arm_elapsed_at_recovery_seconds": sum(elapsed) if all_durations_known else None,
        "execution": "sequential_randomized",
    }
    connection.execute("UPDATE run_budgets SET ledger_json=? WHERE run_id=?",
                       (_encode(ledger), report["run_id"]))


def _assert_no_live_owner(connection, pair_id):
    if not _has_pair_owner_table(connection):
        return
    owner = connection.execute(
        "SELECT execution_status,owner_pid FROM faithful_intervention_pair_owners WHERE pair_id=?",
        (pair_id,),
    ).fetchone()
    if owner is None or owner[0] not in {"scheduled", "running"}:
        return
    if owner[1] != os.getpid() and _pid_is_running(owner[1]):
        raise FaithfulInterventionError("intervention_pair_execution_active")
    try:
        from ..faithful_intervention_control import _worker_alive

        if _worker_alive(pair_id):
            raise FaithfulInterventionError("intervention_pair_execution_active")
    except ImportError:
        return


def _pid_is_running(pid):
    if type(pid) is not int or pid < 1:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _has_pair_owner_table(connection):
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='faithful_intervention_pair_owners'"
    ).fetchone() is not None


def _elapsed_seconds(started_at_utc):
    if not isinstance(started_at_utc, str):
        return None
    try:
        started = datetime.fromisoformat(started_at_utc)
        return max(0.0, (datetime.now(UTC) - started).total_seconds())
    except ValueError:
        return None
