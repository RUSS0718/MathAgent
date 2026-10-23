"""S3 control predicate inside the mathematical SQLite write transaction."""

import time

from ..run_control import RunStopped


def controlled_patch(connection, run_id, event, updates):
    """Serialize math progress against cancel; late call audit never advances math."""
    if not connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='workspace_jobs'"
    ).fetchone():
        return updates
    job = connection.execute("SELECT status FROM workspace_jobs WHERE job_id=?", (run_id,)).fetchone()
    if job is None:  # Standalone Harness remains a separate, explicit API.
        return updates
    deadline = connection.execute(
        "SELECT json_extract(ledger_json,'$.deadline_at') FROM run_budgets WHERE run_id=?", (run_id,)
    ).fetchone()
    stopped = job[0] != "running"
    expired = deadline is not None and time.time() >= deadline[0]
    if not stopped and not expired:
        return updates
    if event["type"] == "call_audit" and set(updates) <= {"calls", "status"}:
        return {"calls": updates["calls"]} if "calls" in updates else {}
    raise RunStopped("run_deadline_exhausted" if expired else "run_stopped")
