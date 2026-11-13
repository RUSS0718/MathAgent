"""Authenticated necessary-input control sharing the Job/Solver transaction."""

import json
import time

from flask import g, jsonify, request

from .faithful_task import public_run_result
from .run_budget import freeze_budget
from .run_control import RunStopped
from .solver_harness.storage import SolverRevisionConflictError, SolverStateStore
from .workspace import WorkspaceError, _is_uuid_v4, _json, _request_digest, _utc_now


def pending_question(connection, job_id):
    """Read only the persisted question; never infer one from model prose."""
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='solver_states'").fetchone():
        return None
    row = connection.execute("SELECT state_json FROM solver_states WHERE run_id=?", (job_id,)).fetchone()
    return json.loads(row[0]).get("clarification") if row else None


def _deadline(connection, job_id):
    return connection.execute(
        "SELECT json_extract(ledger_json,'$.deadline_at') FROM run_budgets WHERE run_id=?",
        (job_id,)).fetchone()


def expired_reply(connection, row, question):
    saved = json.loads(row["result_json"] or "{}").get("faithful", {}).get("clarification_reply")
    if saved:
        return saved
    if row["status"] != "failed" or not question or "answer" not in question:
        return None
    deadline = _deadline(connection, row["job_id"])
    if (row["error_code"] == "run_deadline_exhausted"
            or (question["status"] == "evaluating" and deadline and time.time() >= deadline[0])):
        return {**question, "status": "expired"}
    return None


def clarification_actions(connection, row):
    """Advertise question-specific operations without admitting generic resume."""
    question = pending_question(connection, row["job_id"])
    if expired_reply(connection, row, question):
        return ["create_new_task"]
    if not question or question["status"] != "waiting":
        return None
    if row["status"] != "waiting_input":
        return []
    deadline = _deadline(connection, row["job_id"])
    if deadline is None:
        return ["cancel"]
    return ["cancel", "save_clarification" if time.time() >= deadline[0] else "answer_clarification"]


def save_answer(service, *, user_id, job_id, request_id, payload, key):
    """Claim an answer once and queue semantic intake within the old budget."""
    if not _is_uuid_v4(key):
        raise WorkspaceError("idempotency_key_invalid")
    answer = payload.get("answer")
    if not isinstance(answer, str) or not answer.strip() or len(answer) > 8000:
        raise WorkspaceError("clarification_answer_invalid")
    if payload.get("task_id") != job_id or type(payload.get("input_version")) is not int:
        raise WorkspaceError("clarification_identity_conflict", status=409)
    digest = _request_digest("clarification", job_id, request_id, payload)
    store = service.store
    connection = store._connection
    with store._lock:
        row = connection.execute("SELECT * FROM workspace_jobs WHERE job_id=? AND user_id=?",
                                 (job_id, user_id)).fetchone()
        if row is None:
            raise WorkspaceError("job_not_found", status=404)
        prior = connection.execute("SELECT request_digest,response_json FROM workspace_actions "
            "WHERE user_id=? AND idempotency_key=?", (user_id, key)).fetchone()
        if prior:
            if prior[0] != digest:
                raise WorkspaceError("idempotency_conflict", status=409)
            return json.loads(prior[1]), True
        question = pending_question(connection, job_id)
        if (not question or question["request_id"] != request_id
                or question["input_version"] != payload["input_version"]):
            raise WorkspaceError("clarification_version_conflict", status=409)
        identity = json.loads(row["result_json"] or "{}")
        reply = expired_reply(connection, row, question)
        if question["status"] in {"evaluating", "answered"} or reply:
            if (reply or question).get("answer") != answer:
                raise WorkspaceError("clarification_answer_conflict", status=409)
            return (reply or question)["receipt"], True
        if row["status"] != "waiting_input":
            raise WorkspaceError("clarification_not_waiting", status=409)
        deadline = _deadline(connection, job_id)
        if deadline is None:
            raise WorkspaceError("run_budget_unavailable", status=409)
        expired = time.time() >= deadline[0]
        receipt = {"success": True, "job_id": job_id,
                   "status": "failed" if expired else "queued",
                   "answer_saved": True, "continuation": "new_task_required" if expired else "same_task"}

        def persist(control_connection):
            current = control_connection.execute("SELECT status FROM workspace_jobs WHERE job_id=?", (job_id,)).fetchone()
            if current[0] != "waiting_input":
                raise WorkspaceError("clarification_not_waiting", status=409)
            now = _utc_now()
            identity.update(final_response="", verification={"status": "unknown"})
            identity.pop("solver", None)
            if expired:
                identity["faithful"]["clarification_reply"] = {
                    **question, "status": "expired", "answer": answer, "receipt": receipt}
                freeze_budget(control_connection, job_id)
            error = "run_deadline_exhausted" if expired else None
            control_connection.execute("UPDATE workspace_jobs SET status=?,result_json=?,error_code=?,updated_at=? WHERE job_id=?",
                (receipt["status"], _json(identity), error, now, job_id))
            snapshot = json.loads(control_connection.execute("SELECT snapshot_json FROM runs WHERE run_id=?", (job_id,)).fetchone()[0])
            snapshot.update(status="FAILED" if expired else "QUEUED", result=public_run_result(identity),
                            final_response="", updated_at=now)
            control_connection.execute("UPDATE runs SET snapshot_json=?,updated_at=? WHERE run_id=?",
                                       (_json(snapshot), now, job_id))
            control_connection.execute("INSERT INTO workspace_actions VALUES(?,?,?,?,?,?,?)",
                (user_id, key, "clarification", job_id, digest, _json(receipt), now))
            store._insert_event(job_id, "timeout" if expired else "resumed", {
                "type": "timeout" if expired else "resumed", "status": receipt["status"],
                "request_id": request_id, "input_version": payload["input_version"],
                "continuation": receipt["continuation"]})

        if expired:
            connection.execute("BEGIN IMMEDIATE")
            try:
                persist(connection)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        else:
            state_store = SolverStateStore(connection)
            run = state_store.get_run(job_id)
            event = {"event_id": f"{request_id}:received", "type": "clarification_received",
                     "clarification_request_id": request_id}
            updates = {"clarification": {**question, "status": "evaluating", "answer": answer, "receipt": receipt},
                       "status": "running", "final_response": ""}
            try:
                state_store.commit_event(job_id, expected_revision=run["state_revision"],
                    event=event, state_updates=updates, request_hash=digest,
                    transaction_hook=persist)
            except SolverRevisionConflictError as exc:
                updated = pending_question(connection, job_id)
                if (updated and updated.get("request_id") == request_id
                        and updated.get("status") in {"evaluating", "answered"}
                        and updated.get("answer") == answer):
                    return updated["receipt"], True
                raise WorkspaceError("clarification_version_conflict", status=409) from exc
            except RunStopped as exc:
                if exc.category == "run_deadline_exhausted":
                    return save_answer(service, user_id=user_id, job_id=job_id,
                                       request_id=request_id, payload=payload, key=key)
                raise WorkspaceError("clarification_not_waiting", status=409) from exc
    if not expired:
        service.resubmit(job_id)
    return receipt, False


def create_related_task(service, *, user_id, job_id, request_id, key):
    """Explicitly start a linked task from the original problem and saved reply."""
    with service.store._lock:
        row = service.store._connection.execute(
            "SELECT * FROM workspace_jobs WHERE job_id=? AND user_id=?", (job_id, user_id)).fetchone()
        if row is None:
            raise WorkspaceError("job_not_found", status=404)
        identity = json.loads(row["result_json"] or "{}")
        connection = service.store._connection
        reply = expired_reply(connection, row, pending_question(connection, job_id))
        if not reply or reply["request_id"] != request_id:
            raise WorkspaceError("clarification_new_task_unavailable", status=409)
    return service.create_job(user_id=user_id, session_id=row["session_id"], idempotency_key=key,
        problem=f"{row['problem']}\n\n补充条件（{reply['question']}）：{reply['answer']}",
        solver_mode=identity["solver_mode"], verification_mode=row["verification_mode"],
        input_user_file_id=row["input_user_file_id"], presentation_mode=identity.get("presentation_mode"),
        formal_policy=identity.get("formal_policy"),
        clarification_source={"task_id": job_id, "request_id": request_id,
                              "input_version": reply["input_version"]})


def register_clarification_api(app, service, *, require_auth, request_object, error_response):
    """Use the existing auth/CSRF middleware and structured WorkspaceError contract."""
    @app.post("/api/agent/jobs/<job_id>/clarifications/<request_id>")
    def answer_clarification(job_id, request_id):
        session = require_auth(g.auth_session)
        payload = request_object()
        if isinstance(payload, tuple):
            return payload
        try:
            result, existing = save_answer(service, user_id=session.user_id, job_id=job_id,
                request_id=request_id, payload=payload, key=request.headers.get("Idempotency-Key", ""))
            if result["continuation"] == "new_task_required":
                return jsonify({**result, "success": False, "existing": existing,
                                "code": "clarification_expired", "error": "clarification_expired"}), 409
            return jsonify({**result, "existing": existing}), 200 if existing else 202
        except WorkspaceError as exc:
            return error_response(exc)

    @app.post("/api/agent/jobs/<job_id>/clarifications/<request_id>/new-task")
    def new_task_from_clarification(job_id, request_id):
        session = require_auth(g.auth_session)
        try:
            job, existing = create_related_task(service, user_id=session.user_id, job_id=job_id,
                request_id=request_id, key=request.headers.get("Idempotency-Key", ""))
            return jsonify({"success": True, "job_id": job["job_id"],
                            "status": job["status"], "existing": existing}), 200 if existing else 202
        except WorkspaceError as exc:
            return error_response(exc)
