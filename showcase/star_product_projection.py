"""Idempotent redacted Solver-to-Job projection, sharing the workspace transaction."""

import json


def current_solver(connection, run_id):
    """Read only public math progress, including after Job projection is sealed."""
    row = connection.execute("SELECT state_json FROM solver_states WHERE run_id=?", (run_id,)).fetchone()
    if row is None:
        return None
    from .star_product_pipeline import projection

    state = json.loads(row[0])
    return projection({"run_id": run_id, "state_revision": state["state_revision"], "state": state})


def project_solver_event(connection, job_id, event):
    if event.get("type") != "solver_progress":
        return True
    connection.execute("BEGIN IMMEDIATE")
    row = connection.execute(
        "SELECT status,result_json FROM workspace_jobs WHERE job_id=?", (job_id,)
    ).fetchone()
    if row[0] in {"succeeded", "failed", "canceled"}:
        connection.rollback()
        return False
    duplicate = connection.execute(
        "SELECT 1 FROM workspace_events WHERE job_id=? AND event_type='solver_progress' "
        "AND json_extract(payload_json, '$.solver_event_id')=?",
        (job_id, event["solver_event_id"]),
    ).fetchone()
    if duplicate:
        connection.rollback()
        return False
    result = {**json.loads(row[1]), "solver": event["solver"]}
    connection.execute("UPDATE workspace_jobs SET result_json=? WHERE job_id=?",
                       (json.dumps(result, ensure_ascii=False), job_id))
    row = connection.execute("SELECT snapshot_json FROM runs WHERE run_id=?", (job_id,)).fetchone()
    snapshot = json.loads(row[0])
    snapshot["result"] = result
    connection.execute("UPDATE runs SET snapshot_json=? WHERE run_id=?",
                       (json.dumps(snapshot, ensure_ascii=False), job_id))
    return True
