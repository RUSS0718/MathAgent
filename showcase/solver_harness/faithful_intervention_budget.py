"""Atomically reserve two arms against their parent Run's budget ledger."""

from __future__ import annotations

import json
import time

from ..run_budget import BudgetExhausted, _summary


def reserve_pair_budget(connection, run_id, pair_id, calls):
    """Reserve symmetric model/HTTP/token ceilings inside the caller's transaction."""
    row = connection.execute(
        "SELECT ledger_json FROM run_budgets WHERE run_id=?", (run_id,)
    ).fetchone()
    if row is None:
        raise BudgetExhausted("budget_uninitialized")
    ledger = json.loads(row[0])
    summary = _summary(ledger)
    now = time.time()
    if now >= ledger["deadline_at"]:
        raise BudgetExhausted("run_deadline_exhausted")
    logical_count = len(calls) * 2
    http_count = sum(call["http_attempts"] for call in calls) * 2
    token_hold = sum(
        (call["input_estimate"] + call["output_cap"]) * call["http_attempts"] * 2
        for call in calls
    )
    limits = ledger["limits"]
    parent = connection.execute("SELECT state_json FROM solver_states WHERE run_id=?", (run_id,)).fetchone()
    floor = (json.loads(parent[0]).get("route_budget", {}).get("closing_reserve", {})
             if parent else {})
    if not floor:
        has_control_schema = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            ("faithful_intervention_control",),
        ).fetchone()
        if has_control_schema:
            control = connection.execute(
                "SELECT closing_reserve_json FROM faithful_intervention_control "
                "WHERE run_id=? AND status='paused'", (run_id,),
            ).fetchone()
            if control is not None and control[0]:
                frozen = json.loads(control[0])
                floor = {key: frozen.get(key) for key in
                         ("model_calls", "http_attempts", "tokens", "tool_calls", "time_seconds")}
    tool_count = sum(call.get("tool_calls", 0) for call in calls) * 2
    time_hold = sum(call.get("time_seconds", 0) for call in calls) * 2
    if summary["tool_calls"] + tool_count + floor.get("tool_calls", 0) > limits["max_tool_calls"]:
        raise BudgetExhausted("run_tool_budget_exhausted")
    time_holds = ledger.get("intervention_time_holds", {})
    pending_time = sum(sum(arms.values()) for arms in time_holds.values())
    if time_hold + pending_time + floor.get("time_seconds", 0) > ledger["deadline_at"] - now:
        raise BudgetExhausted("intervention_time_reserve_unavailable")
    if (summary["logical_calls"] + logical_count + floor.get("model_calls", 0) > limits["max_model_calls"]
            or summary["http_attempts"] + http_count + floor.get("http_attempts", 0) > limits["max_http_attempts"]
            or summary["charged_tokens"] + token_hold + floor.get("tokens", 0) > limits["max_tokens"]):
        raise BudgetExhausted("run_model_call_budget_exhausted")

    if time_hold:
        ledger.setdefault("intervention_time_holds", {})[pair_id] = {
            arm: time_hold / 2 for arm in ("control", "intervention")}

    for arm in ("control", "intervention"):
        arm_role = f"faithful_intervention:{pair_id}:{arm}"
        for index in range(tool_count // 2):
            ledger["actions"].append({
                "id": f"faithful:{pair_id}:{arm}:tool:{index}", "kind": "tool",
                "logical_call_id": None, "solver_call_id": None, "role": arm_role,
                "tool_call_id": None, "input_estimate": 0, "output_cap": 0,
                "reservation_id": pair_id, "status": "pre_reserved",
                "usage": {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None},
            })
        for index, call in enumerate(calls):
            logical_id = f"faithful:{pair_id}:{arm}:logical:{index}"
            ledger["actions"].append({
                "id": logical_id,
                "kind": "logical",
                "logical_call_id": logical_id,
                "solver_call_id": None,
                "role": arm_role,
                "tool_call_id": None,
                "input_estimate": 0,
                "output_cap": 0,
                "reservation_id": pair_id,
                "status": "pre_reserved",
                "usage": {"prompt_tokens": None, "completion_tokens": None,
                          "total_tokens": None},
            })
            for attempt in range(call["http_attempts"]):
                ledger["actions"].append({
                    "id": f"faithful:{pair_id}:{arm}:http:{index}:{attempt}",
                    "kind": "http",
                    "logical_call_id": logical_id,
                    "solver_call_id": None,
                    "role": arm_role,
                    "tool_call_id": None,
                    "input_estimate": call["input_estimate"],
                    "output_cap": call["output_cap"],
                    "reservation_id": pair_id,
                    "status": "pre_reserved",
                    "usage": {"prompt_tokens": None, "completion_tokens": None,
                              "total_tokens": None},
                })
    connection.execute(
        "UPDATE run_budgets SET ledger_json=? WHERE run_id=?",
        (json.dumps(ledger, ensure_ascii=False, sort_keys=True, separators=(",", ":")), run_id),
    )
    return {
        "logical_calls": logical_count,
        "http_attempts": http_count,
        "token_ceiling": token_hold,
        "tool_calls": tool_count,
        "time_seconds": time_hold,
        "deadline_at": ledger["deadline_at"],
        "arm_roles": {
            arm: f"faithful_intervention:{pair_id}:{arm}"
            for arm in ("control", "intervention")
        },
    }


def arm_budget_snapshot(connection, run_id, pair_id, arm):
    """Project only this pair arm's actual and unresolved parent-ledger entries."""
    row = connection.execute(
        "SELECT ledger_json FROM run_budgets WHERE run_id=?", (run_id,)
    ).fetchone()
    if row is None:
        raise BudgetExhausted("budget_uninitialized")
    ledger = json.loads(row[0])
    role = f"faithful_intervention:{pair_id}:{arm}"
    logical = [item for item in ledger["actions"]
               if item.get("reservation_id") == pair_id and item.get("role") == role
               and item.get("kind") == "logical"]
    http = [item for item in ledger["actions"]
            if item.get("reservation_id") == pair_id and item.get("role") == role
            and item.get("kind") == "http"]
    attempts = [item for item in http if item.get("status") != "pre_reserved"]
    tools = [item for item in ledger["actions"]
             if item.get("reservation_id") == pair_id and item.get("role") == role
             and item.get("kind") == "tool"]
    actual_tools = [item for item in tools if item.get("status") != "pre_reserved"]
    usage = {}
    for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
        values = [item.get("usage", {}).get(field) for item in attempts]
        usage[field] = None if any(value is None for value in values) else sum(values)
    unknown = sum(
        item.get("status") in {"unknown", "reserved", "pending", "error"}
        or any(item.get("usage", {}).get(field) is None
               for field in ("prompt_tokens", "completion_tokens", "total_tokens"))
        for item in attempts
    )
    return {
        "logical_calls": sum(item.get("status") != "pre_reserved" for item in logical),
        "native_roles": sorted({item["native_role"] for item in logical
                                if item.get("status") != "pre_reserved" and item.get("native_role")}),
        "http_attempts": len(attempts),
        "tool_calls": len(actual_tools),
        "tool_wall_time_seconds": sum(item.get("duration_seconds", 0) for item in actual_tools),
        "unknown_tool_calls": _summary({**ledger, "actions": actual_tools})["unknown_tool_calls"],
        "provider_usage": usage,
        "unknown_attempts": unknown,
        "unresolved_attempts": sum(
            item.get("status") in {"reserved", "pending", "error", "unknown"}
            for item in attempts
        ),
        "unused_holds": sum(item.get("status") == "pre_reserved" for item in logical + http + tools),
        "deadline_at": ledger["deadline_at"],
    }


def release_unused_arm_holds(connection, run_id, pair_id, arm):
    """Release only slots still pre-reserved after the synchronous executor returns."""
    owns_transaction = not connection.in_transaction
    if owns_transaction:
        connection.execute("BEGIN IMMEDIATE")
    try:
        row = connection.execute(
            "SELECT ledger_json FROM run_budgets WHERE run_id=?", (run_id,)
        ).fetchone()
        if row is None:
            raise BudgetExhausted("budget_uninitialized")
        ledger = json.loads(row[0])
        role = f"faithful_intervention:{pair_id}:{arm}"
        retained = [item for item in ledger["actions"] if not (
            item.get("reservation_id") == pair_id and item.get("role") == role
            and item.get("status") == "pre_reserved"
        )]
        released = len(ledger["actions"]) - len(retained)
        ledger["actions"] = retained
        held_time = ledger.get("intervention_time_holds", {}).get(pair_id)
        uncertain = any(item.get("reservation_id") == pair_id and item.get("role") == role
                        and item.get("kind") in {"http", "tool"}
                        and (item.get("status") in {"unknown", "reserved", "pending", "error"}
                             or (item.get("execution_evidence") or {}).get("unknown_outcome") is True
                             or (item.get("status") == "timeout" and not (
                                 (item.get("execution_evidence") or {}).get("cleanup_verified") is True
                                 and (item.get("execution_evidence") or {}).get("unknown_outcome") is False)))
                        for item in retained)
        if held_time is not None and not uncertain:
            held_time.pop(arm, None)
        connection.execute(
            "UPDATE run_budgets SET ledger_json=? WHERE run_id=?",
            (json.dumps(ledger, ensure_ascii=False, sort_keys=True, separators=(",", ":")), run_id),
        )
        if owns_transaction:
            connection.commit()
        return released
    except BaseException:
        if owns_transaction:
            connection.rollback()
        raise
