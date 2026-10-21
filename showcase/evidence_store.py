"""Atomic persistence of appended final-answer checks in both public projections."""
from __future__ import annotations

import json

from .final_evidence import append_verification


def append_check(connection, job_id, result, now, error_type, record_event):
    connection.execute("BEGIN IMMEDIATE")
    try:
        row = connection.execute("SELECT status,result_json FROM workspace_jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            raise error_type("job_not_found", status=404)
        if row["status"] in {"queued", "running", "waiting_input"}:
            raise error_type("verification_requires_terminal_job", status=409)
        stored = json.loads(row["result_json"]) if row["result_json"] else {}
        stored["verification"] = append_verification(stored.get("final_response", ""), stored.get("verification", {}), result)
        connection.execute("UPDATE workspace_jobs SET result_json=?,updated_at=? WHERE job_id=?", (json.dumps(stored, ensure_ascii=False), now, job_id))
        run = connection.execute("SELECT snapshot_json FROM runs WHERE run_id=?", (job_id,)).fetchone()
        if run:
            snapshot = json.loads(run["snapshot_json"])
            snapshot["result"] = stored
            snapshot["updated_at"] = now
            connection.execute("UPDATE runs SET snapshot_json=?,updated_at=? WHERE run_id=?", (json.dumps(snapshot, ensure_ascii=False), now, job_id))
        record_event()
        connection.commit()
    except Exception:
        connection.rollback()
        raise
