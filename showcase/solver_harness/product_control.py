"""S3 control predicate inside the mathematical SQLite write transaction."""

import json
import time

from ..run_control import RunStopped
from ..star_product_modes import BEST_EFFORT_MODES


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
    if expired and not stopped and _expired_selection(connection, run_id, event, updates):
        return updates
    if event["type"] == "call_audit" and set(updates) <= {"calls", "status"}:
        return {"calls": updates["calls"]} if "calls" in updates else {}
    raise RunStopped("run_deadline_exhausted" if expired else "run_stopped")


def _expired_selection(connection, run_id, event, updates):
    """Permit only a recomputed pure terminal selection after the S3 deadline."""
    from .best_effort import select_best_effort

    mode = connection.execute(
        "SELECT json_extract(result_json,'$.solver_mode') FROM workspace_jobs WHERE job_id=?",
        (run_id,),
    ).fetchone()[0]
    if mode not in BEST_EFFORT_MODES or event["type"] not in {
        "best_effort_selected", "best_effort_empty"
    }:
        return False
    state = json.loads(connection.execute(
        "SELECT state_json FROM solver_states WHERE run_id=?", (run_id,),
    ).fetchone()[0])
    if state.get("best_effort_decision") is not None:
        return False
    budget = {**state.get("budget", {}), "exhaustion_reason": "runtime_budget_exhausted"}
    events = [json.loads(row[0]) for row in connection.execute(
        "SELECT event_json FROM solver_events WHERE run_id=? ORDER BY sequence", (run_id,),
    )]
    decision = select_best_effort({**state, "budget": budget, "_events": events})
    selected = decision["selected_source_record"]
    expected = {
        "phase": "TERMINAL", "status": "partial_budget_exhausted",
        "best_effort_decision": decision, "finalization_reason": "runtime_budget_exhausted",
        "budget": budget,
        "final_response": selected["answer_text"] if selected else "未能在预算内求得合格的完整答案。",
    }
    return updates == expected and event.get("usage_source") == "no_additional_calls"
