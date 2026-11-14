"""Atomic task lineage and dispatch fencing for arbitrary changed input."""

import json

from flask import g, jsonify, request

from .run_budget import freeze_budget, http_outcome_unknown, tool_outcome_unknown
from .workspace import WorkspaceError, _json, _run_snapshot, _utc_now


def submission_rows(connection, user_id, key):
    """Resolve canonical submissions and committed revision replay receipts."""
    return connection.execute(
        "SELECT j.* FROM workspace_jobs j WHERE j.user_id=? AND (j.idempotency_key=? OR j.job_id IN "
        "(SELECT job_id FROM workspace_actions WHERE user_id=? AND idempotency_key=? "
        "AND operation='revision_submission'))", (user_id, key, user_id, key)).fetchall()


def prepare_revision(store, source, *, user_id, session_id, digest, idempotency_key):
    """Fence the parent inside the same transaction that accepts its successor."""
    connection = store._connection
    row = connection.execute("SELECT * FROM workspace_jobs WHERE job_id=? AND user_id=?",
                             (source["task_id"], user_id)).fetchone()
    if row is None:
        raise WorkspaceError("job_not_found", status=404)
    identity = json.loads(row["result_json"] or "{}")
    faithful = identity.get("faithful")
    if not faithful or row["session_id"] != session_id:
        raise WorkspaceError("task_revision_unavailable", status=409)
    prior = faithful.get("revision_to")
    if prior:
        if prior["request_digest"] != digest:
            raise WorkspaceError("task_revision_conflict", status=409)
        if connection.execute("SELECT 1 FROM workspace_actions WHERE user_id=? AND idempotency_key=?",
                              (user_id, idempotency_key)).fetchone():
            raise WorkspaceError("idempotency_conflict", status=409)
        connection.execute(
            "INSERT INTO workspace_actions(user_id,idempotency_key,operation,job_id,request_digest,response_json,created_at) "
            "VALUES(?,?,'revision_submission',?,?,?,?)",
            (user_id, idempotency_key, prior["task_id"], digest, "{}", _utc_now()))
        return connection.execute("SELECT * FROM workspace_jobs WHERE job_id=?",
                                  (prior["task_id"],)).fetchone()
    from .clarification_api import pending_question

    question = pending_question(connection, row["job_id"])
    version = (question["input_version"] + int(question["status"] == "answered")
               if question else faithful["input_version"])
    if source["input_version"] != version:
        raise WorkspaceError("task_revision_version_conflict", status=409)
    if row["status"] in {"queued", "running", "waiting_input"}:
        now = _utc_now()
        freeze_budget(connection, row["job_id"])
        connection.execute("UPDATE workspace_jobs SET status='canceled',updated_at=? WHERE job_id=?",
                           (now, row["job_id"]))
        connection.execute("UPDATE runs SET snapshot_json=?,updated_at=? WHERE run_id=?",
            (_json(_run_snapshot(row["job_id"], "CANCELED", now,
                execution_mode=identity["execution_mode"], result=identity,
                input_text=row["problem"])), now, row["job_id"]))
        store._insert_event(row["job_id"], "canceled", {
            "type": "canceled", "status": "canceled", "scope": "future_dispatch",
            "remote_request": "cannot_revoke", "reason": "task_revised"})
    return None


def link_revision(store, source, job_id, digest):
    """Persist the reverse link without copying any answer or proof evidence."""
    connection = store._connection
    row = connection.execute("SELECT result_json FROM workspace_jobs WHERE job_id=?",
                             (source["task_id"],)).fetchone()
    result = json.loads(row[0])
    result["faithful"]["revision_to"] = {"task_id": job_id, "request_digest": digest}
    connection.execute("UPDATE workspace_jobs SET result_json=? WHERE job_id=?",
                       (_json(result), source["task_id"]))
    snapshot = json.loads(connection.execute("SELECT snapshot_json FROM runs WHERE run_id=?",
                                            (source["task_id"],)).fetchone()[0])
    snapshot.setdefault("result", {}).setdefault("faithful", {})["revision_to"] = {"task_id": job_id}
    connection.execute("UPDATE runs SET snapshot_json=? WHERE run_id=?", (_json(snapshot), source["task_id"]))


def _remote_slots(ledger):
    """Count possibly executing actions, not missing usage or known failures."""
    count = 0
    for action in ledger["actions"]:
        attempt = action.get("public_attempt") or {}
        if action["kind"] == "http" and attempt.get("dispatch_status") != "not_submitted":
            count += (action["status"] in {"reserved", "pending"} or http_outcome_unknown(action))
        elif action["kind"] == "tool":
            count += tool_outcome_unknown(action)
    return count


def revision_capacity_available(connection, job_id, worker_capacity):
    """Count unresolved remote Runs as occupied slots even after local stop."""
    row = connection.execute("SELECT result_json FROM workspace_jobs WHERE job_id=?", (job_id,)).fetchone()
    if not json.loads(row[0] or "{}").get("faithful", {}).get("revision_source"):
        return True
    occupied = {row[0]: 1 for row in connection.execute(
        "SELECT job_id FROM workspace_jobs WHERE status='running' AND job_id!=?", (job_id,))}
    for run_id, ledger in connection.execute(
            "SELECT b.run_id,b.ledger_json FROM run_budgets b JOIN workspace_jobs j ON j.job_id=b.run_id "
            "WHERE b.run_id!=?", (job_id,)):
        occupied[run_id] = max(occupied.get(run_id, 0), _remote_slots(json.loads(ledger)))
    return sum(occupied.values()) < worker_capacity


def wake_revision_jobs(service):
    """Recheck queued successors when an actual worker finishes settlement."""
    with service.store._lock:
        rows = service.store._connection.execute("SELECT job_id FROM workspace_jobs WHERE status='queued' "
            "AND json_extract(result_json,'$.faithful.revision_source') IS NOT NULL").fetchall()
    for row in rows:
        service.resubmit(row[0])


def register_revision_api(app, service, *, require_auth, request_object, error_response):
    """Keep arbitrary changes separate from the versioned clarification API."""
    @app.post("/api/agent/jobs/<job_id>/revisions")
    def revise_task(job_id):
        session = require_auth(g.auth_session)
        payload = request_object()
        if isinstance(payload, tuple):
            return payload
        message, version = payload.get("message"), payload.get("input_version")
        if not isinstance(message, str) or not message.strip() or len(message.strip()) > 100_000:
            return error_response(WorkspaceError("message_must_be_non_empty"))
        if type(version) is not int or version < 1:
            return error_response(WorkspaceError("task_revision_version_conflict", status=409))
        try:
            with service.store._lock:
                row = service.store._connection.execute(
                    "SELECT * FROM workspace_jobs WHERE job_id=? AND user_id=?", (job_id, session.user_id)).fetchone()
                if row is None:
                    raise WorkspaceError("job_not_found", status=404)
                identity = json.loads(row["result_json"] or "{}")
            formal_policy = identity.get("formal_policy")
            if isinstance(formal_policy, dict) and formal_policy.get("source", {}).get("generation_call_id"):
                # A generated target belongs to the old input; intake must regenerate it.
                formal_policy = None
            job, existing = service.create_job(user_id=session.user_id, session_id=row["session_id"],
                problem=message.strip(), idempotency_key=request.headers.get("Idempotency-Key", ""),
                solver_mode=identity.get("solver_mode", "legacy"), verification_mode=row["verification_mode"],
                input_user_file_id=row["input_user_file_id"], presentation_mode=identity.get("presentation_mode"),
                formal_policy=formal_policy,
                revision_source={"task_id": job_id, "input_version": version})
            return jsonify({"success": True, "job_id": job["job_id"], "status": job["status"],
                            "existing": existing}), 200 if existing else 202
        except WorkspaceError as exc:
            return error_response(exc)
