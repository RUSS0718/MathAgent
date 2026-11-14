"""Authenticated public contracts for native Faithful Intervention experiments."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path

from flask import g, jsonify, request

from .faithful_intervention_control import (
    assert_applied_config,
    authorize_explicit_resume,
    ensure_control_schema,
    register_worker,
    unregister_worker,
)
from .solver_harness.faithful_intervention import FaithfulInterventionEngine
from .solver_harness.faithful_intervention_records import FaithfulInterventionError
from .workspace import WorkspaceError, _is_uuid_v4

_CATEGORIES = {
    "method_mismatch", "lemma_structure", "decomposition_granularity",
    "inefficient_order", "underused_premise",
}
_STATUSES = {"active", "falsified", "confirmed", "retired"}
_SCHEMA_LOCK = threading.RLock()


def pause_admission(row, pipeline):
    """Shared read-only qualification for the existing pause route."""
    from .star_product_modes import BEST_EFFORT_MODES, STAR_MODES

    if row is None or row["status"] != "running":
        raise WorkspaceError("intervention_parent_not_running", status=409)
    identity = json.loads(row["result_json"] or "{}")
    if (pipeline is None or pipeline.intervention_enabled is not True
            or identity.get("solver_mode") not in STAR_MODES - BEST_EFFORT_MODES):
        raise WorkspaceError("intervention_parent_not_eligible", status=409)
    features = pipeline.preset_config(identity["solver_mode"])["features"]
    if (features.get("problem_spec") is not True or features.get("serial_routes") is not True
            or features.get("concurrent_routes") is True):
        raise WorkspaceError("intervention_parent_not_eligible", status=409)


def resume_intervention_admission(connection, row):
    """Preview dedicated parent resume without authorizing or resolving a pair."""
    from .clarification_api import pending_question
    from .star_product_recovery import authorize_resume, resume_budget

    job_id = row["job_id"]
    control = _paused(connection, job_id)
    _assert_paused_checkpoint(connection, job_id, control["checkpoint_revision"],
                              control["applied_config_fingerprint"])
    question = pending_question(connection, job_id)
    if question and question["status"] == "waiting":
        raise WorkspaceError("clarification_answer_required", status=409)
    resume_budget(connection, job_id)
    authorize_resume(connection, row, None, read_only=True)
    return authorize_explicit_resume(connection, job_id, read_only=True)


def register_faithful_intervention_api(app, database_path: str | Path, *, enabled: bool) -> None:
    """Register job-owned routes; integration supplies server-only native factories."""
    if not enabled:
        return
    database_path = str(database_path)

    with closing(sqlite3.connect(database_path, timeout=5, check_same_thread=False)) as connection:
        connection.row_factory = sqlite3.Row
        if database_path != ":memory:":
            # Keep report snapshots from blocking pair settlement writes.
            connection.execute("PRAGMA journal_mode=WAL").fetchone()
        with _SCHEMA_LOCK:
            ensure_control_schema(connection)
            connection.executescript(
                "CREATE TABLE IF NOT EXISTS faithful_intervention_hypothesis_metadata ("
                "hypothesis_id TEXT PRIMARY KEY,job_id TEXT NOT NULL,public_id TEXT NOT NULL,"
                "metadata_json TEXT NOT NULL,UNIQUE(job_id,public_id));"
                "CREATE TABLE IF NOT EXISTS faithful_intervention_action_metadata ("
                "action_id TEXT PRIMARY KEY,job_id TEXT NOT NULL,public_id TEXT NOT NULL,"
                "metadata_json TEXT NOT NULL,UNIQUE(job_id,public_id));"
                "CREATE TABLE IF NOT EXISTS faithful_intervention_pair_metadata ("
                "pair_id TEXT PRIMARY KEY,job_id TEXT NOT NULL,public_id TEXT NOT NULL,"
                "UNIQUE(job_id,public_id));"
            )
            FaithfulInterventionEngine(connection, connection_lock=_SCHEMA_LOCK)

    def connect(write=False):
        connection = sqlite3.connect(database_path, timeout=5, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        return connection

    def owned_job(connection, job_id):
        session = g.auth_session
        if session is None:
            raise WorkspaceError("auth_required", status=401)
        row = connection.execute(
            "SELECT 1 FROM workspace_jobs WHERE job_id=? AND user_id=?", (job_id, session.user_id)
        ).fetchone()
        if row is None:
            raise WorkspaceError("job_not_found", status=404)
        return session.user_id

    def engine(connection):
        # The request connection has already opened its snapshot transaction.
        # Avoid schema DDL on that connection while other pair writes are active.
        return FaithfulInterventionEngine(
            connection, connection_lock=_SCHEMA_LOCK, initialize_schema=False
        )

    def fail(error):
        if isinstance(error, WorkspaceError):
            raise error
        if isinstance(error, FaithfulInterventionError):
            code = str(error)
            status = 409 if code.endswith(("conflict", "unavailable", "required")) else 400
            raise WorkspaceError(code, status=status) from error
        if isinstance(error, KeyError):
            raise WorkspaceError(str(error).strip("'"), status=404) from error
        raise error

    @app.get("/api/agent/jobs/<job_id>/interventions")
    def get_interventions(job_id):
        with closing(connect()) as connection:
            owned_job(connection, job_id)
            data = projection(connection, job_id)
            connection.commit()
        response = jsonify({"success": True, "interventions": data})
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/api/agent/jobs/<job_id>/interventions/pause")
    def request_pause(job_id):
        body = _body()
        if body:
            raise WorkspaceError("intervention_request_invalid")
        with closing(connect(write=True)) as connection:
            owned_job(connection, job_id)
            _ensure_feature_enabled(app)
            row = connection.execute(
                "SELECT status,result_json FROM workspace_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            runtime = app.extensions.get("showcase_workspace_service")
            pipeline = getattr(runtime, "star_pipeline", None)
            pause_admission(row, pipeline)
            connection.execute(
                "INSERT INTO faithful_intervention_control(job_id,run_id,status,updated_at) "
                "VALUES(?,?,'pause_requested',?) ON CONFLICT(job_id) DO UPDATE SET "
                "status='pause_requested',resume_authorized=0,updated_at=excluded.updated_at "
                "WHERE faithful_intervention_control.status NOT IN ('paused','pause_requested')",
                (job_id, job_id, time.time()),
            )
            connection.commit()
        return jsonify({"success": True, "job_id": job_id, "status": "pause_requested"}), 202

    @app.post("/api/agent/jobs/<job_id>/interventions/hypotheses")
    def create_hypothesis(job_id):
        body = _body()
        required = {"hypothesis_id", "failure_category", "source_event_id", "source_state_revision",
                    "affected_roots", "failure_symptom", "diagnostic_evidence", "candidate_action_ids",
                    "falsification_criteria", "priority"}
        if set(body) != required:
            raise WorkspaceError("intervention_hypothesis_request_invalid")
        with closing(connect(write=True)) as connection:
            owned_job(connection, job_id)
            control = _paused(connection, job_id)
            checkpoint = _checkpoint(connection, job_id, control["checkpoint_revision"])
            metadata, source_event = _validate_hypothesis(body, connection, job_id, checkpoint)
            internal_id = f"{job_id}:{body['hypothesis_id']}"
            value = {
                "hypothesis_id": internal_id,
                "failure_category": body["failure_category"],
                "evidence": {"source_metadata": metadata, "diagnostic_evidence": body["diagnostic_evidence"]},
                "candidate_action_ids": [f"{job_id}:{item}" for item in body["candidate_action_ids"]],
                "falsification_criteria": body["falsification_criteria"],
            }
            existing = connection.execute(
                "SELECT hypothesis_id,metadata_json FROM faithful_intervention_hypothesis_metadata "
                "WHERE job_id=? AND public_id=?", (job_id, body["hypothesis_id"]),
            ).fetchone()
            if existing is not None:
                stored = engine(connection).get_hypothesis(existing["hypothesis_id"])
                if (_encode({**stored.__dict__, "candidate_action_ids": list(stored.candidate_action_ids)})
                        != _encode({**value, "candidate_action_ids": value["candidate_action_ids"]})
                        or json.loads(existing["metadata_json"]) != metadata):
                    raise WorkspaceError("intervention_registration_identity_conflict", status=409)
                connection.commit()
                return jsonify({"success": True, "hypothesis_id": body["hypothesis_id"],
                                "source_event_id": body["source_event_id"],
                                "source_state_revision": source_event["state_revision"],
                                "status": "active"}), 200
            try:
                connection.commit()

                def persist_metadata(db):
                    _assert_paused_checkpoint(
                        db, job_id, checkpoint["state_revision"], control["applied_config_fingerprint"]
                    )
                    db.execute(
                        "INSERT INTO faithful_intervention_hypothesis_metadata VALUES(?,?,?,?)",
                        (internal_id, job_id, body["hypothesis_id"], _encode(metadata)),
                    )

                engine(connection).register_hypothesis(value, transaction_hook=persist_metadata)
            except (ValueError, KeyError, sqlite3.IntegrityError) as error:
                fail(error)
        return jsonify({"success": True, "hypothesis_id": body["hypothesis_id"],
                        "source_event_id": body["source_event_id"],
                        "source_state_revision": source_event["state_revision"],
                        "status": "active"}), 201

    @app.patch("/api/agent/jobs/<job_id>/interventions/hypotheses/<hypothesis_id>")
    def update_hypothesis(job_id, hypothesis_id):
        body = _body()
        if set(body) != {"status"} or body.get("status") not in _STATUSES:
            raise WorkspaceError("intervention_hypothesis_status_invalid")
        with closing(connect(write=True)) as connection:
            owned_job(connection, job_id)
            row = connection.execute(
                "SELECT hypothesis_id,metadata_json FROM faithful_intervention_hypothesis_metadata "
                "WHERE job_id=? AND public_id=?", (job_id, hypothesis_id),
            ).fetchone()
            if row is None:
                raise WorkspaceError("hypothesis_not_found", status=404)
            metadata = json.loads(row["metadata_json"])
            metadata["status"] = body["status"]
            connection.execute("UPDATE faithful_intervention_hypothesis_metadata SET metadata_json=? WHERE hypothesis_id=?",
                               (_encode(metadata), row["hypothesis_id"]))
            connection.commit()
        return jsonify({"success": True, "hypothesis_id": hypothesis_id, "status": body["status"]})

    @app.post("/api/agent/jobs/<job_id>/interventions/actions")
    def create_action(job_id):
        body = _body()
        if set(body) != {"action_id", "action_type", "target", "parameters"}:
            raise WorkspaceError("intervention_action_request_invalid")
        if (not all(isinstance(body[key], str) and body[key].strip() for key in ("action_id", "action_type", "target"))
                or not isinstance(body["parameters"], dict)):
            raise WorkspaceError("intervention_action_request_invalid")
        with closing(connect(write=True)) as connection:
            owned_job(connection, job_id)
            control = _paused(connection, job_id)
            checkpoint = _checkpoint(connection, job_id, control["checkpoint_revision"])
            normalized = _validate_action(body, checkpoint)
            internal_id = f"{job_id}:{body['action_id']}"
            existing = connection.execute(
                "SELECT action_id FROM faithful_intervention_action_metadata "
                "WHERE job_id=? AND public_id=?", (job_id, body["action_id"]),
            ).fetchone()
            if existing is not None:
                stored = engine(connection).get_action(existing["action_id"])
                if (stored.action_type != normalized["action_type"]
                        or stored.target != normalized["target"]
                        or dict(stored.parameters) != normalized["parameters"]):
                    raise WorkspaceError("intervention_registration_identity_conflict", status=409)
                connection.commit()
                return jsonify({"success": True, "action_id": body["action_id"]}), 200
            try:
                connection.commit()

                def persist_metadata(db):
                    _assert_paused_checkpoint(
                        db, job_id, checkpoint["state_revision"], control["applied_config_fingerprint"]
                    )
                    db.execute("INSERT INTO faithful_intervention_action_metadata VALUES(?,?,?,?)",
                               (internal_id, job_id, body["action_id"],
                                _encode({"action_type": normalized["action_type"],
                                         "target": "current_step"})))

                engine(connection).register_action(
                    {**normalized, "action_id": internal_id}, transaction_hook=persist_metadata
                )
            except (ValueError, KeyError, sqlite3.IntegrityError) as error:
                fail(error)
        return jsonify({"success": True, "action_id": body["action_id"]}), 201

    @app.post("/api/agent/jobs/<job_id>/interventions/pairs")
    def reserve_pair(job_id):
        body = _body()
        required = {"pair_id", "hypothesis_id", "control_action_id", "intervention_action_id", "seed"}
        if set(body) != required or type(body.get("seed")) is not int or body["seed"] < 0:
            raise WorkspaceError("intervention_pair_request_invalid")
        estimator = app.config.get("SHOWCASE_FAITHFUL_INTERVENTION_RESERVATION_ESTIMATOR")
        if not callable(estimator):
            raise WorkspaceError("intervention_server_reservation_unavailable", status=409)
        with closing(connect(write=True)) as connection:
            owned_job(connection, job_id)
            control = _paused(connection, job_id)
            checkpoint = _checkpoint(connection, job_id, control["checkpoint_revision"])
            hypothesis = _owned_hypothesis(connection, job_id, body["hypothesis_id"])
            actions = [_owned_action(connection, job_id, body[key]) for key in
                       ("control_action_id", "intervention_action_id")]
            pair_id = f"{job_id}:{body['pair_id']}"
            existing = connection.execute(
                "SELECT pair_id FROM faithful_intervention_pair_metadata "
                "WHERE job_id=? AND public_id=?", (job_id, body["pair_id"]),
            ).fetchone()
            if existing is not None:
                current = engine(connection).get_pair(existing["pair_id"])
                if (existing["pair_id"] != pair_id
                        or current["checkpoint_revision"] != control["checkpoint_revision"]
                        or current["hypothesis_id"] != hypothesis
                        or current["seed"] != body["seed"]
                        or current["arms"]["control"]["action_id"] != actions[0]
                        or current["arms"]["intervention"]["action_id"] != actions[1]):
                    raise WorkspaceError("intervention_pair_identity_conflict", status=409)
                connection.commit()
                return jsonify({"success": True, "pair_id": body["pair_id"],
                                "status": current["status"],
                                "budget_reservation": current.get("budget_reservation")}), 200
            try:
                measured = estimator(connection, checkpoint, hypothesis, actions)
            except (TypeError, ValueError, KeyError, sqlite3.Error) as error:
                raise WorkspaceError(
                    "intervention_server_reservation_unavailable", status=409
                ) from error
            if not isinstance(measured, dict) or set(measured) != {
                "input_estimate", "output_cap", "model_calls", "http_attempts", "tool_calls", "time_seconds"
            }:
                raise WorkspaceError("intervention_server_reservation_invalid", status=409)
            gate = _parent_gate(job_id, control["checkpoint_revision"], control["applied_config_fingerprint"])
            try:
                connection.commit()

                def persist_pair_metadata(db):
                    db.execute("INSERT OR IGNORE INTO faithful_intervention_pair_metadata VALUES(?,?,?)",
                               (pair_id, job_id, body["pair_id"]))
                    db.execute("INSERT OR IGNORE INTO faithful_intervention_pair_owners "
                               "(pair_id,job_id,execution_status,updated_at) VALUES(?,?,?,?)",
                               (pair_id, job_id, "reserved", time.time()))

                report = engine(connection).reserve_pair(
                    job_id=job_id, job_gate=gate, run_id=job_id,
                    expected_revision=control["checkpoint_revision"],
                    hypothesis_id=hypothesis, control_action_id=actions[0],
                    intervention_action_id=actions[1], pair_id=pair_id,
                    seed=body["seed"], reservation=measured,
                    transaction_hook=persist_pair_metadata,
                )
            except (ValueError, KeyError, sqlite3.IntegrityError, sqlite3.OperationalError) as error:
                fail(error)
        return jsonify({"success": True, "pair_id": body["pair_id"], "status": report["status"],
                        "budget_reservation": report.get("budget_reservation")}), 201

    @app.post("/api/agent/jobs/<job_id>/interventions/pairs/<pair_id>/execute")
    def execute_pair(job_id, pair_id):
        if _body():
            raise WorkspaceError("intervention_request_invalid")
        factory = app.config.get("SHOWCASE_FAITHFUL_INTERVENTION_EXECUTION_FACTORY")
        with closing(connect(write=True)) as connection:
            owned_job(connection, job_id)
            owned = connection.execute(
                "SELECT pair_id FROM faithful_intervention_pair_metadata WHERE job_id=? AND public_id=?",
                (job_id, pair_id),
            ).fetchone()
            if owned is None:
                raise WorkspaceError("pair_not_found", status=404)
            control = _paused(connection, job_id)
            if not callable(factory):
                raise WorkspaceError("intervention_native_executor_unavailable", status=409)
            current = engine(connection).get_pair(owned[0])
            if current["status"] != "reserved":
                raise WorkspaceError("intervention_pair_not_executable", status=409)
            _parent_gate(job_id, control["checkpoint_revision"], control["applied_config_fingerprint"]).assert_paused(
                connection=connection, job_id=job_id, run_id=job_id,
                checkpoint_revision=control["checkpoint_revision"],
            )
            connection.execute(
                "UPDATE faithful_intervention_pair_owners SET owner_pid=?,owner_started=?,execution_status='scheduled',updated_at=? "
                "WHERE pair_id=? AND execution_status='reserved'",
                (__import__("os").getpid(), time.time(), time.time(), owned[0]),
            )
            if connection.execute("SELECT changes()").fetchone()[0] != 1:
                raise WorkspaceError("intervention_pair_execution_active", status=409)
            thread = threading.Thread(
                target=_execute_async, args=(app, database_path, job_id, owned[0], factory), daemon=True
            )
            register_worker(owned[0], thread)
            try:
                connection.commit()
                thread.start()
            except BaseException as error:
                unregister_worker(owned[0])
                if connection.in_transaction:
                    connection.rollback()
                else:
                    connection.execute(
                        "UPDATE faithful_intervention_pair_owners SET owner_pid=NULL,owner_started=NULL,"
                        "execution_status='reserved',updated_at=? WHERE pair_id=? AND execution_status='scheduled'",
                        (time.time(), owned[0]),
                    )
                    connection.commit()
                raise WorkspaceError("intervention_worker_start_failed", status=503) from error
        return jsonify({"success": True, "pair_id": pair_id, "status": "scheduled"}), 202

    @app.get("/api/agent/jobs/<job_id>/interventions/reports")
    def get_intervention_reports(job_id):
        with closing(connect()) as connection:
            owned_job(connection, job_id)
            value = projection(connection, job_id)
            connection.commit()
        response = jsonify({"success": True, "reports": value["pairs"], "effects": value["effects"]})
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/api/agent/jobs/<job_id>/interventions/resume")
    def resume_parent(job_id):
        body = _body()
        if body:
            raise WorkspaceError("intervention_request_invalid")
        service = app.extensions["showcase_workspace_service"]
        session = g.auth_session
        idempotency_key = request.headers.get("Idempotency-Key", "")
        if not _is_uuid_v4(idempotency_key):
            raise WorkspaceError("idempotency_key_invalid", status=400)
        with closing(connect(write=True)) as connection:
            owned_job(connection, job_id)
            from .workspace import _request_digest

            saved = connection.execute(
                "SELECT operation,job_id,request_digest,response_json FROM workspace_actions "
                "WHERE user_id=? AND idempotency_key=?", (session.user_id, idempotency_key)
            ).fetchone()
            if saved is not None:
                if (saved["operation"] != "resume" or saved["job_id"] != job_id
                        or saved["request_digest"] != _request_digest("resume", job_id, "", None)):
                    raise WorkspaceError("idempotency_conflict", status=409)
                return jsonify({**json.loads(saved["response_json"]), "existing": True}), 200
            row = connection.execute("SELECT * FROM workspace_jobs WHERE job_id=?", (job_id,)).fetchone()
            resume_intervention_admission(connection, row)
            authorize_explicit_resume(connection, job_id)
            connection.commit()
        try:
            result, existing = service.resume_job(
                user_id=session.user_id, job_id=job_id,
                idempotency_key=idempotency_key,
            )
        except WorkspaceError:
            raise
        return jsonify({**result, "existing": existing}), 200 if existing else 202


def projection(connection, job_id):
    """Whitelist one Job's hypotheses, action rankings, pair receipts and aggregate."""
    owned = connection.execute("SELECT 1 FROM workspace_jobs WHERE job_id=?", (job_id,)).fetchone()
    if owned is None:
        raise WorkspaceError("job_not_found", status=404)
    from .solver_harness.faithful_intervention_effects import aggregate_pairs

    hypotheses, actions, pairs = [], [], []
    engine = FaithfulInterventionEngine(
        connection, connection_lock=_SCHEMA_LOCK, initialize_schema=False
    )
    state_row = connection.execute(
        "SELECT state_json,state_revision FROM solver_states WHERE run_id=?", (job_id,)
    ).fetchone()
    failure_sources, root_obligations, current_method_id = [], [], None
    if state_row is not None:
        from .solver_harness.storage import SolverStateStore
        from .star_product_events import public_solver_event_id

        run = SolverStateStore(connection).get_run(job_id)
        state = run["state"]
        steps = (state.get("plan") or {}).get("steps", [])
        step_ordinals = {item["step_id"]: f"步骤 {index}"
                         for index, item in enumerate(steps, 1)}
        current_step = state.get("current_step")
        step = next((item for item in steps if item.get("step_id") == current_step), None)
        current_method_id = step.get("method_id") if isinstance(step, dict) else None
        failure_sources = [
            {
                "source_event_id": public_solver_event_id(run, event),
                "source_state_revision": event["state_revision"],
                "event_type": "step_reviewed",
                "verdict": event["verdict"],
                "step_label": step_ordinals.get(event.get("step_id"), "未标记步骤"),
            }
            for event in run["events"]
            if event.get("type") == "step_reviewed" and event.get("valid") is True
            and event.get("verdict") in {"CHALLENGE", "TRACE_BACK", "PROPOSE_REPLAN"}
        ]
        root_obligations = [
            {"obligation_id": item["obligation_id"], "proposition": item["statement"]}
            for item in state.get("problem_spec", {}).get("root_obligations", [])
            if isinstance(item, dict) and isinstance(item.get("obligation_id"), str)
            and isinstance(item.get("statement"), str)
        ]
    for row in connection.execute(
        "SELECT m.hypothesis_id,m.public_id,m.metadata_json,h.payload_json "
        "FROM faithful_intervention_hypothesis_metadata m JOIN faithful_intervention_hypotheses h "
        "ON h.hypothesis_id=m.hypothesis_id WHERE m.job_id=? ORDER BY m.public_id", (job_id,),
    ):
        metadata, hypothesis = json.loads(row["metadata_json"]), json.loads(row["payload_json"])
        ranking = []
        if state_row is not None:
            from .solver_harness.faithful_intervention_records import _normalize_hypothesis
            from .solver_harness.storage import SolverStateStore
            run = SolverStateStore(connection).get_run(job_id)
            from .solver_harness.faithful_intervention_actions import registered_action_ranking
            ranking = registered_action_ranking(engine, run, _normalize_hypothesis(hypothesis))
        hypotheses.append({
            "hypothesis_id": row["public_id"], "failure_category": hypothesis["failure_category"],
            "source": {key: metadata.get(key) for key in
                       ("source_event_id", "source_state_revision", "checkpoint_revision")},
            "affected_roots": metadata["affected_roots"], "failure_symptom": metadata["failure_symptom"],
            "diagnostic_evidence": hypothesis["evidence"].get("diagnostic_evidence"),
            "candidate_action_ids": [item["action_id"].split(":", 1)[-1] for item in ranking],
            "priority": metadata["priority"], "status": metadata["status"],
            "falsification_criteria": hypothesis["falsification_criteria"], "action_ranking": ranking,
        })
    for row in connection.execute(
        "SELECT action_id,public_id,metadata_json FROM faithful_intervention_action_metadata "
        "WHERE job_id=? ORDER BY public_id", (job_id,),
    ):
        actions.append({"action_id": row["public_id"], **json.loads(row["metadata_json"])})
    for row in connection.execute(
        "SELECT pair_id,public_id FROM faithful_intervention_pair_metadata WHERE job_id=? ORDER BY public_id",
        (job_id,),
    ):
        report = engine.get_pair(row["pair_id"])
        pairs.append(_public_pair(report, row["public_id"]))
    effects = aggregate_pairs(engine, run_id=job_id)
    return {"job_id": job_id, "status": _control_status(connection, job_id),
            "checkpoint_revision": _checkpoint_revision(connection, job_id),
            "failure_sources": failure_sources, "root_obligations": root_obligations,
            "current_method_id": current_method_id,
            "hypotheses": hypotheses, "actions": actions, "pairs": pairs, "effects": effects}


def _validate_hypothesis(body, connection, job_id, checkpoint):
    category = body["failure_category"]
    if category not in _CATEGORIES:
        raise WorkspaceError("hypothesis_category_noncausal")
    if type(body["source_state_revision"]) is not int or body["source_state_revision"] > checkpoint["state_revision"]:
        raise WorkspaceError("intervention_source_revision_invalid")
    if not isinstance(body["source_event_id"], str) or not body["source_event_id"].strip():
        raise WorkspaceError("intervention_source_event_required")
    # Public callers must cite the same scoped alias exposed by the Job projection.
    from .solver_harness.storage import SolverStateStore
    from .star_product_events import public_solver_event_id
    run = SolverStateStore(connection).get_run(job_id)
    row = next((item for item in connection.execute(
        "SELECT event_id,state_revision,event_json FROM solver_events WHERE run_id=?", (job_id,)
    ) if public_solver_event_id(run, json.loads(item["event_json"])) == body["source_event_id"]), None)
    if row is None or row["state_revision"] != body["source_state_revision"]:
        raise WorkspaceError("intervention_source_event_not_found", status=404)
    event = json.loads(row["event_json"])
    if (event.get("type") != "step_reviewed"
            or event.get("verdict") not in {"CHALLENGE", "TRACE_BACK", "PROPOSE_REPLAN"}
            or event.get("valid") is not True):
        raise WorkspaceError("intervention_source_not_mathematical_failure")
    failure = body["failure_symptom"]
    diagnostic = body["diagnostic_evidence"]
    diagnostic_fields = {"event_type", "verdict"}
    if (not isinstance(failure, str) or not failure.strip()
            or not isinstance(diagnostic, dict) or not diagnostic
            or set(diagnostic) - diagnostic_fields
            or diagnostic.get("event_type") != event["type"]
            or diagnostic.get("verdict") != event["verdict"]):
        raise WorkspaceError("intervention_structured_failure_invalid")
    roots = body["affected_roots"]
    available = {
        item["obligation_id"]: item["statement"]
        for item in checkpoint["state"].get("problem_spec", {}).get("root_obligations", [])
        if isinstance(item, dict) and isinstance(item.get("obligation_id"), str)
        and isinstance(item.get("statement"), str)
    }
    if not isinstance(roots, list) or not roots or any(
        not isinstance(item, dict) or set(item) != {"obligation_id", "proposition"}
        or item["obligation_id"] not in available or not isinstance(item["proposition"], str)
        or item["proposition"] != available[item["obligation_id"]]
        or not item["proposition"].strip() for item in roots
    ):
        raise WorkspaceError("intervention_affected_roots_invalid")
    if type(body["priority"]) is not int or not 0 <= body["priority"] <= 100:
        raise WorkspaceError("intervention_priority_invalid")
    if not isinstance(body["candidate_action_ids"], list) or len(body["candidate_action_ids"]) < 2:
        raise WorkspaceError("intervention_candidate_actions_invalid")
    if not isinstance(body["falsification_criteria"], dict) or not body["falsification_criteria"]:
        raise WorkspaceError("intervention_falsification_criteria_required")
    metadata = {
        "source_event_id": body["source_event_id"], "source_state_revision": row["state_revision"],
        "checkpoint_revision": checkpoint["state_revision"], "affected_roots": roots,
        "failure_symptom": failure.strip(), "priority": body["priority"], "status": "active",
    }
    return metadata, row


def _validate_action(body, checkpoint):
    state = checkpoint["state"]
    step = next((item for item in state.get("plan", {}).get("steps", [])
                 if item.get("step_id") == state.get("current_step")), None)
    target = state.get("current_step") if body["target"] == "current_step" else body["target"]
    if (state.get("phase") != "STEP_EXECUTE" or not isinstance(state.get("problem_spec"), dict)
            or state.get("route_policy", {}).get("enabled") is not True
            or step is None or body["action_type"] != "reasoning_method"
            or target != state.get("current_step")
            or set(body["parameters"]) != {"method_id"}):
        raise WorkspaceError("native_action_not_supported")
    from .solver_harness.progress import METHOD_IDS
    if body["parameters"]["method_id"] not in METHOD_IDS - {"unknown"}:
        raise WorkspaceError("native_action_not_supported")
    return {**body, "target": target}


def _paused(connection, job_id):
    row = connection.execute(
        "SELECT * FROM faithful_intervention_control WHERE job_id=? AND status='paused'", (job_id,)
    ).fetchone()
    if row is None:
        raise WorkspaceError("intervention_parent_not_paused", status=409)
    return row


def _checkpoint(connection, job_id, revision):
    row = connection.execute("SELECT state_json,state_revision FROM solver_states WHERE run_id=?", (job_id,)).fetchone()
    if row is None or row["state_revision"] != revision:
        raise WorkspaceError("intervention_checkpoint_revision_conflict", status=409)
    return {"state": json.loads(row["state_json"]), "state_revision": row["state_revision"]}


def _assert_paused_checkpoint(connection, job_id, revision, config_fingerprint):
    control = _paused(connection, job_id)
    job = connection.execute("SELECT status FROM workspace_jobs WHERE job_id=?", (job_id,)).fetchone()
    state = connection.execute(
        "SELECT state_revision FROM solver_states WHERE run_id=?", (job_id,)
    ).fetchone()
    if (job is None or job[0] != "waiting_input" or state is None
            or state[0] != revision or control["checkpoint_revision"] != revision
            or control["applied_config_fingerprint"] != config_fingerprint):
        raise WorkspaceError("intervention_parent_pause_identity_mismatch", status=409)


def _owned_hypothesis(connection, job_id, public_id):
    row = connection.execute("SELECT hypothesis_id FROM faithful_intervention_hypothesis_metadata WHERE job_id=? AND public_id=?",
                             (job_id, public_id)).fetchone()
    if row is None:
        raise WorkspaceError("hypothesis_not_found", status=404)
    return row[0]


def _owned_action(connection, job_id, public_id):
    row = connection.execute("SELECT action_id FROM faithful_intervention_action_metadata WHERE job_id=? AND public_id=?",
                             (job_id, public_id)).fetchone()
    if row is None:
        raise WorkspaceError("action_not_found", status=404)
    return row[0]


def _parent_gate(job_id, revision, fingerprint):
    class Gate:
        def assert_paused(self, *, connection, job_id: str, run_id: str, checkpoint_revision: int):
            control = _paused(connection, job_id)
            row = connection.execute("SELECT status FROM workspace_jobs WHERE job_id=?", (job_id,)).fetchone()
            state = connection.execute("SELECT state_revision FROM solver_states WHERE run_id=?", (run_id,)).fetchone()
            if (row is None or row[0] != "waiting_input" or run_id != job_id
                    or checkpoint_revision != revision or state is None or state[0] != revision
                    or control["checkpoint_revision"] != revision
                    or control["applied_config_fingerprint"] != fingerprint):
                raise WorkspaceError("intervention_parent_pause_identity_mismatch", status=409)
    return Gate()


def _execute_async(app, database_path, job_id, pair_id, factory):
    with closing(sqlite3.connect(database_path, timeout=5, check_same_thread=False)) as connection:
        connection.row_factory = sqlite3.Row
        try:
            engine = FaithfulInterventionEngine(
                connection, connection_lock=_SCHEMA_LOCK, initialize_schema=False
            )
            report = engine.get_pair(pair_id)
            control = _paused(connection, job_id)
            gate = _parent_gate(job_id, control["checkpoint_revision"], control["applied_config_fingerprint"])
            executor, ledger = factory(connection, job_id, pair_id, report, gate)
            applied = executor.model_port.adapter.applied_config()
            assert_applied_config(connection, job_id, applied)
            from .solver_harness.faithful_intervention_native import execute_native_pair
            execute_native_pair(engine, pair_id, executor=executor, ledger=ledger, job_gate=gate)
            connection.execute("UPDATE faithful_intervention_pair_owners SET execution_status='completed',updated_at=? WHERE pair_id=?",
                               (time.time(), pair_id))
            connection.commit()
        except BaseException:
            connection.rollback()
            try:
                connection.execute(
                    "UPDATE faithful_intervention_pair_owners SET execution_status='interrupted',updated_at=? "
                    "WHERE pair_id=? AND execution_status IN ('scheduled','running')",
                    (time.time(), pair_id),
                )
                connection.commit()
            except sqlite3.Error:
                connection.rollback()
        finally:
            unregister_worker(pair_id)


def _public_pair(report, public_id):
    arms = {}
    for key, value in report.get("arms", {}).items():
        arms[key] = {name: value.get(name) for name in (
            "status", "measurement", "cost", "duration_seconds", "evidence_integrity",
            "branch_verifier_verdict", "independent_recheck_verdict",
        ) if name in value}
        action = value.get("action_id")
        arms[key]["action_id"] = action.split(":", 1)[-1] if isinstance(action, str) else None
        arms[key]["branch_id"] = value.get("branch_id")
    return {key: report.get(key) for key in (
        "status", "checkpoint_revision", "checkpoint_hash", "seed", "order", "denominator",
        "evaluable_pairs", "incomplete_pairs", "unknown_pairs", "effect", "budget_reservation",
        "branch_engine", "parent_resume", "policy_version", "problem_hash", "config_hash",
        "primary_metric", "uncertainty_method",
    ) if key in report} | {"pair_id": public_id, "arms": arms}


def _control_status(connection, job_id):
    row = connection.execute("SELECT status FROM faithful_intervention_control WHERE job_id=?", (job_id,)).fetchone()
    return row[0] if row else "unpaused"


def _checkpoint_revision(connection, job_id):
    row = connection.execute("SELECT checkpoint_revision FROM faithful_intervention_control WHERE job_id=?", (job_id,)).fetchone()
    return row[0] if row else None


def _ensure_feature_enabled(app):
    if app.config.get("SHOWCASE_FAITHFUL_INTERVENTION_ENABLED") is not True:
        raise WorkspaceError("not_found", status=404)


def _body():
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise WorkspaceError("body_must_be_object")
    return value


def _encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
