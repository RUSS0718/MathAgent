"""Read a committed Job snapshot without waiting for an in-process writer."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from .job_observation import observe_deadline
from .run_budget import _summary
from .star_product_modes import STAR_MODES
from .star_product_projection import current_solver


def read_job(service, job_id, user_id):
    """Keep memory/legacy reads; isolate file-backed STAR reads from writers."""
    store = service.store
    if service.star_pipeline is not None and store.database_path != ":memory:":
        return read_job_snapshot(store, job_id, user_id)
    payload = store.get_job(job_id, user_id)
    star = (payload.get("result") or {}).get("solver_mode") in STAR_MODES
    if star:
        with store._lock:
            payload["result"]["solver"] = current_solver(store._connection, job_id)
    attempts = [event["data"]["attempt"] for event in store.events(job_id, user_id)
                if event["event"] == "request_attempt"]
    budget, ledger_attempts = service.budget_ledger.view(job_id) if service.budget_ledger is not None else (None, [])
    return _with_accounting(payload, attempts, budget, ledger_attempts, star)


def _with_accounting(payload, attempts, budget, ledger_attempts, star):
    if budget is not None and (star or not (payload.get("result") or {}).get("budget")):
        payload["result"] = {**(payload.get("result") or {}), "budget": budget}
    attempts = list({item["attempt_id"]: item for item in [*attempts, *ledger_attempts]}.values())
    if attempts:
        payload["result"] = {**(payload.get("result") or {}), "request_attempts": attempts}
    if star:
        observe_deadline(payload, ledger_attempts, budget)
    return payload


def read_job_snapshot(store, job_id, user_id):
    """Use one authorized SQLite read transaction; never infer an uncommitted result."""
    from .workspace import WorkspaceError

    uri = Path(store.database_path).resolve().as_uri() + "?mode=ro"
    # A RESERVED writer permits reads; a brief commit may hold EXCLUSIVE.
    # Match the ledger reader's bounded busy timeout for that commit window.
    with closing(sqlite3.connect(uri, uri=True, timeout=1)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN")
        row = connection.execute(
            "SELECT * FROM workspace_jobs WHERE job_id=? AND user_id=?", (job_id, user_id)
        ).fetchone()
        if row is None:
            raise WorkspaceError("job_not_found", status=404)
        payload = store._job_payload(row, include_result=True)
        events = connection.execute(
            "SELECT event_id,event_type,payload_json FROM workspace_events WHERE job_id=? ORDER BY event_id",
            (job_id,),
        ).fetchall()
        payload["last_event_id"] = events[-1]["event_id"] if events else 0
        star = (payload.get("result") or {}).get("solver_mode") in STAR_MODES
        if star:
            payload["result"]["solver"] = current_solver(connection, job_id)
        attempts = [json.loads(event["payload_json"])["attempt"] for event in events
                    if event["event_type"] == "request_attempt"]
        ledger = connection.execute("SELECT ledger_json FROM run_budgets WHERE run_id=?", (job_id,)).fetchone()
        budget, ledger_attempts = None, []
        if ledger is not None:
            state = json.loads(ledger[0])
            budget = _summary(state)
            ledger_attempts = [action["public_attempt"] for action in state["actions"]
                               if action.get("public_attempt")]
        return _with_accounting(payload, attempts, budget, ledger_attempts, star)
