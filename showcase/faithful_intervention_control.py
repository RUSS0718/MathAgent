"""Durable safe-checkpoint pause controls for native interventions."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from datetime import UTC, datetime
from threading import RLock, Thread

from .workspace import WorkspaceError

_WORKER_LOCK = RLock()
_WORKERS: dict[str, Thread] = {}


class InterventionPaused(BaseException):
    """Stop the worker only after a safe Solver event boundary is committed."""


def ensure_control_schema(connection: sqlite3.Connection) -> None:
    was_in_transaction = connection.in_transaction
    connection.execute(
        "CREATE TABLE IF NOT EXISTS faithful_intervention_control ("
        "job_id TEXT PRIMARY KEY,run_id TEXT NOT NULL,status TEXT NOT NULL,"
        "checkpoint_revision INTEGER,config_json TEXT,applied_config_json TEXT,"
        "applied_config_fingerprint TEXT,closing_reserve_json TEXT,"
        "resume_authorized INTEGER NOT NULL DEFAULT 0,updated_at REAL NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS faithful_intervention_pair_owners ("
        "pair_id TEXT PRIMARY KEY,job_id TEXT NOT NULL,owner_pid INTEGER,"
        "owner_started REAL,execution_status TEXT NOT NULL,updated_at REAL NOT NULL)"
    )
    if not was_in_transaction:
        connection.commit()


def maybe_pause(connection, run, event, config, problem, *, applied_config=None,
                harness=None, model_port=None):
    """Freeze config and revision after STEP_EXECUTE with no pending dispatch."""
    run_id = run.get("run_id")
    state = run.get("state") if isinstance(run, dict) else None
    if not isinstance(run_id, str) or not isinstance(state, dict):
        return None
    ensure_control_schema(connection)
    row = connection.execute(
        "SELECT status FROM faithful_intervention_control WHERE job_id=? AND run_id=?",
        (run_id, run_id),
    ).fetchone()
    if row is None or row[0] != "pause_requested":
        return None
    if event.get("type") != "step_dispatched" or state.get("phase") != "STEP_EXECUTE":
        return None
    pending = state.get("pending_call") or state.get("pending_calls")
    inflight = any(
        isinstance(call, dict) and call.get("status") in {"dispatched", "unknown_outcome"}
        for call in (state.get("calls") or {}).values()
    )
    if pending or inflight:
        return None
    revision = run.get("state_revision")
    if type(revision) is not int:
        return None
    config = _with_measured_closing_reserve(config, run, problem, harness, model_port)
    safe_config = _json_safe_config({
        key: value for key, value in config.items() if key != "trusted_closing_reserve"
    })
    applied = applied_config or (config.get("applied_model_config") if isinstance(config, dict) else None)
    if not isinstance(applied, dict) or not applied:
        raise WorkspaceError("intervention_applied_model_config_unavailable", status=409)
    applied_json = _encode(applied)
    fingerprint = hashlib.sha256(applied_json.encode()).hexdigest()
    closing, source = _closing_reserve(state, config)
    connection.execute("BEGIN IMMEDIATE")
    try:
        current = connection.execute(
            "SELECT state_revision,state_json FROM solver_states WHERE run_id=?", (run_id,)
        ).fetchone()
        if current is None or current[0] != revision:
            raise WorkspaceError("intervention_checkpoint_revision_conflict", status=409)
        current_state = json.loads(current[1])
        if current_state != state:
            raise WorkspaceError("intervention_checkpoint_revision_conflict", status=409)
        connection.execute(
            "UPDATE faithful_intervention_control SET status='paused',checkpoint_revision=?,"
            "config_json=?,applied_config_json=?,applied_config_fingerprint=?,"
            "closing_reserve_json=?,resume_authorized=0,updated_at=? WHERE job_id=? AND status='pause_requested'",
            (revision, _encode(safe_config), applied_json, fingerprint,
             _encode({"source": source, **closing}), time.time(), run_id),
        )
        changed = connection.execute("SELECT changes()").fetchone()[0]
        if changed != 1:
            raise WorkspaceError("intervention_pause_not_requested", status=409)
        connection.execute(
            "UPDATE workspace_jobs SET status='waiting_input',updated_at=? WHERE job_id=? AND status='running'",
            (_utc_now(), run_id),
        )
        _append_pause_event(connection, run_id, revision)
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    raise InterventionPaused()


def resume_guard(connection, job_id, *, read_only=False):
    """Reject ordinary parent resume while an F4 pair owns its checkpoint."""
    if not read_only:
        ensure_control_schema(connection)
    row = connection.execute(
        "SELECT status,resume_authorized FROM faithful_intervention_control WHERE job_id=?",
        (job_id,),
    ).fetchone()
    if row is None:
        return True
    if row[0] not in {"paused", "resuming"}:
        raise WorkspaceError("intervention_parent_not_paused", status=409)
    pairs_exist = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='faithful_intervention_pairs'"
    ).fetchone()
    pairs = connection.execute(
        "SELECT p.pair_id,p.report_json,o.execution_status,o.owner_pid,o.owner_started "
        "FROM faithful_intervention_pairs p JOIN faithful_intervention_pair_owners o "
        "ON o.pair_id=p.pair_id WHERE o.job_id=?", (job_id,),
    ).fetchall() if pairs_exist else []
    unresolved = []
    for pair_id, report_json, execution_status, owner_pid, owner_started in pairs:
        raw = json.loads(report_json)
        if raw.get("status") in {"reserved", "running"}:
            if _owner_alive(pair_id, owner_pid, execution_status):
                raise WorkspaceError("intervention_pair_execution_active", status=409)
            unresolved.append(pair_id)
    if unresolved:
        raise WorkspaceError("intervention_pair_resolution_required", status=409)
    if row[0] == "paused" or row[1] != 1:
        raise WorkspaceError("intervention_explicit_resume_required", status=409)
    return True


def authorize_explicit_resume(connection, job_id):
    """Authorize the dedicated intervention resume route after pair resolution."""
    ensure_control_schema(connection)
    owns_transaction = not connection.in_transaction
    if owns_transaction:
        connection.execute("BEGIN IMMEDIATE")
    try:
        row = connection.execute(
            "SELECT status FROM faithful_intervention_control WHERE job_id=?", (job_id,)
        ).fetchone()
        if row is None or row[0] != "paused":
            raise WorkspaceError("intervention_parent_not_paused", status=409)
        pairs_exist = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='faithful_intervention_pairs'"
        ).fetchone()
        pairs = connection.execute(
            "SELECT p.pair_id,p.report_json,o.owner_pid,o.execution_status "
            "FROM faithful_intervention_pairs p "
            "JOIN faithful_intervention_pair_owners o ON o.pair_id=p.pair_id WHERE o.job_id=?",
            (job_id,),
        ).fetchall() if pairs_exist else []
        for pair_id, report_json, owner_pid, execution_status in pairs:
            if json.loads(report_json).get("status") in {"reserved", "running"}:
                if _owner_alive(pair_id, owner_pid, execution_status):
                    raise WorkspaceError("intervention_pair_execution_active", status=409)
                _interrupt_pair(connection, pair_id, job_id)
        connection.execute(
            "UPDATE faithful_intervention_control SET status='resuming',resume_authorized=1,updated_at=? "
            "WHERE job_id=? AND status='paused'",
            (time.time(), job_id),
        )
        if connection.execute("SELECT changes()").fetchone()[0] != 1:
            raise WorkspaceError("intervention_parent_not_paused", status=409)
        if owns_transaction:
            connection.commit()
    except BaseException:
        if owns_transaction:
            connection.rollback()
        raise
def assert_applied_config(connection, job_id, applied_config):
    row = connection.execute(
        "SELECT applied_config_fingerprint FROM faithful_intervention_control WHERE job_id=?",
        (job_id,),
    ).fetchone()
    fingerprint = hashlib.sha256(_encode(applied_config).encode()).hexdigest()
    if row is None or not row[0] or row[0] != fingerprint:
        raise WorkspaceError("intervention_applied_config_drift", status=409)
    return fingerprint


def _closing_reserve(state, config):
    route = state.get("route_budget") or {}
    reserve = route.get("closing_reserve")
    source = "route_budget.closing_reserve"
    if not _valid_reserve(reserve):
        preflight = route.get("preflight") or {}
        reserve = preflight.get("closing_reserve") if isinstance(preflight, dict) else None
        source = "route_budget.preflight.closing_reserve"
    if not _valid_reserve(reserve):
        measured = config.get("trusted_closing_reserve") if isinstance(config, dict) else None
        if isinstance(measured, dict) and _valid_reserve(measured.get("reserve")):
            reserve = measured["reserve"]
            source = measured.get("source")
            if source not in {"route_budget.expansion_budget", "finalize.finalization_reserve_estimate"}:
                raise WorkspaceError("intervention_closing_reserve_source_invalid", status=409)
    if not _valid_reserve(reserve):
        raise WorkspaceError("intervention_closing_reserve_unavailable", status=409)
    return {key: reserve[key] for key in ("model_calls", "http_attempts", "tokens", "tool_calls", "time_seconds")}, source


def _with_measured_closing_reserve(config, run, problem, harness, model_port):
    """Measure the existing finalization floor when the initial route has none yet."""
    state = run["state"]
    if (_valid_reserve((state.get("route_budget") or {}).get("closing_reserve"))
            or _valid_reserve(((state.get("route_budget") or {}).get("preflight") or {}).get("closing_reserve"))
            or _valid_reserve((config.get("trusted_closing_reserve") or {}).get("reserve"))):
        return config
    if harness is None or model_port is None:
        return config
    try:
        from .solver_harness.finalize import (
            finalization_requests,
            finalization_reserve_estimate,
            proof_basis,
            valid_facts,
        )

        history = state.get("final_solution_attempts") or []
        previous_review = history[-1].get("review") if history else None
        session = (
            f"final:{run['run_id']}:plan{state['plan_version']}:attempt{state['attempt_index']}"
            f":candidate{len(history)}"
        )
        generator, review = finalization_requests(
            problem, valid_facts(state), proof_basis(state), session, previous_review, False,
        )
        estimate = finalization_reserve_estimate(
            harness, model_port, run, generator, review, require_cap=True, use_snapshot=True,
        )
        adapter = model_port.adapter
        client = adapter._get_client()
        timeout = adapter.applied_config().get("request_timeout_seconds") or 30
        retries = getattr(client, "retry", None)
        if (type(timeout) not in {int, float} or timeout <= 0
                or type(retries) is not int or retries < 0):
            raise ValueError("finalization_time_estimate_unavailable")
        reserve = {
            "model_calls": estimate["model_calls"],
            "http_attempts": estimate["http_attempts"],
            "tokens": estimate["tokens"],
            "tool_calls": 0,
            "time_seconds": 2 * timeout * (retries + 1),
        }
        return {**config, "trusted_closing_reserve": {
            "source": "finalize.finalization_reserve_estimate", "reserve": reserve,
        }}
    except Exception as error:
        raise WorkspaceError("intervention_closing_reserve_unavailable", status=409) from error


def _valid_reserve(value):
    return isinstance(value, dict) and all(
        type(value.get(key)) in {int, float} and value[key] >= 0
        for key in ("model_calls", "http_attempts", "tokens", "tool_calls", "time_seconds")
    ) and value["model_calls"] >= 2 and value["time_seconds"] > 0


def _json_safe_config(config):
    if not isinstance(config, dict):
        raise WorkspaceError("intervention_config_unavailable", status=409)
    return {key: value for key, value in config.items()
            if not any(token in key.casefold() for token in ("api_key", "secret", "credential", "prompt"))}


def _append_pause_event(connection, job_id, revision):
    now = _utc_now()
    payload = {"type": "intervention_pause_requested", "job_id": job_id,
               "status": "waiting_input", "checkpoint_revision": revision,
               "summary": "运行已在安全步骤边界暂停"}
    cursor = connection.execute(
        "INSERT INTO workspace_events(job_id,event_type,payload_json,created_at) VALUES(?,?,?,?)",
        (job_id, "intervention_pause_requested", _encode({**payload, "created_at": now}), now),
    )
    sequence = connection.execute(
        "SELECT COALESCE(MAX(sequence),0)+1 FROM events WHERE run_id=?", (job_id,)
    ).fetchone()[0]
    connection.execute(
        "INSERT INTO events(run_id,sequence,event_json,created_at) VALUES(?,?,?,?)",
        (job_id, sequence, _encode({**payload, "run_id": job_id, "sequence": sequence,
                                    "workspace_event_id": cursor.lastrowid, "created_at": now}), now),
    )


def register_worker(pair_id, worker):
    with _WORKER_LOCK:
        _WORKERS[pair_id] = worker


def unregister_worker(pair_id):
    with _WORKER_LOCK:
        _WORKERS.pop(pair_id, None)


def _worker_alive(pair_id):
    with _WORKER_LOCK:
        worker = _WORKERS.get(pair_id)
        return worker is not None and (worker.ident is None or worker.is_alive())


def _owner_alive(pair_id, owner_pid, execution_status):
    if execution_status == "interrupted":
        return False
    if owner_pid == os.getpid():
        return _worker_alive(pair_id)
    return _pid_is_running(owner_pid)


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


def _interrupt_pair(connection, pair_id, job_id):
    owns_transaction = not connection.in_transaction
    if owns_transaction:
        connection.execute("BEGIN IMMEDIATE")
    try:
        _interrupt_pair_in_transaction(connection, pair_id, job_id)
        if owns_transaction:
            connection.commit()
    except BaseException:
        if owns_transaction:
            connection.rollback()
        raise


def _interrupt_pair_in_transaction(connection, pair_id, job_id):
    row = connection.execute(
        "SELECT report_json FROM faithful_intervention_pairs WHERE pair_id=?", (pair_id,)
    ).fetchone()
    if row is None:
        return
    from .solver_harness.faithful_intervention_budget import (
        arm_budget_snapshot,
        release_unused_arm_holds,
    )
    from .solver_harness.faithful_intervention_execution import _elapsed_seconds, _save_resources

    report = json.loads(row[0])
    if report.get("status") == "interrupted":
        return
    for arm in ("control", "intervention"):
        record = report["arms"][arm]
        if record.get("status") == "dispatching":
            record["status"] = "unknown_outcome"
            record["duration_seconds"] = _elapsed_seconds(record.get("started_at_utc"))
        elif record.get("status") == "not_started":
            record["duration_seconds"] = 0.0
        release_unused_arm_holds(connection, report["run_id"], pair_id, arm)
        record["cost"] = arm_budget_snapshot(connection, report["run_id"], pair_id, arm)
    report.update(status="interrupted", interruption="worker_process_lost", parent_resume="checkpoint_preserved")
    report["denominator"] = max(report.get("denominator", 0), int(bool(report.get("started_pairs"))))
    connection.execute("UPDATE faithful_intervention_pairs SET report_json=? WHERE pair_id=?",
                       (_encode(report), pair_id))
    connection.execute(
        "UPDATE faithful_intervention_pair_owners SET execution_status='interrupted',updated_at=? WHERE pair_id=?",
        (time.time(), pair_id),
    )
    _save_resources(connection, report)


def _utc_now():
    return datetime.now(UTC).isoformat()


def _encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
