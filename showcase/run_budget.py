"""Atomic persisted Run reservations; provider usage never becomes a local estimate."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from functools import wraps
from pathlib import Path
from typing import Any
from uuid import uuid4

from llm_response import provider_usage, public_attempt

from .run_control import assert_dispatch_allowed, check_control, controlled_action


def public_solver_call_id(run_id, solver_call_id):
    """Pseudonymize step-scoped call IDs before placing them in public evidence."""
    if not isinstance(solver_call_id, str) or not solver_call_id:
        return None
    if ":reasoner:" not in solver_call_id and ":step-verifier:" not in solver_call_id:
        return solver_call_id
    digest = hashlib.sha256(f"{run_id}:{solver_call_id}".encode()).hexdigest()[:32]
    return f"solver_call_{digest}"


@dataclass(frozen=True)
class RunBudgetLimits:
    max_model_calls: int = 6
    max_http_attempts: int = 12
    max_tool_calls: int = 2
    max_tokens: int = 262_144
    max_runtime_seconds: float = 1_100.0

    def __post_init__(self):
        for key in ("max_model_calls", "max_http_attempts", "max_tool_calls", "max_tokens"):
            value = getattr(self, key)
            if type(value) is not int or value < 0:
                raise ValueError("run_budget_limit_invalid")
        value = self.max_runtime_seconds
        if type(value) not in {int, float} or not math.isfinite(value) or value < 0:
            raise ValueError("run_budget_time_invalid")


class BudgetExhausted(RuntimeError):
    category = "run_budget_exhausted"


def scoped_deadline(metadata):
    """Return the earliest explicitly supplied phase or batch Unix deadline."""
    values = [(metadata or {}).get(name) for name in ("phase_deadline_at", "batch_deadline_at")]
    values = [value for value in values if value is not None]
    if any(type(value) not in {int, float} or not math.isfinite(value) for value in values):
        raise BudgetExhausted("invalid_scoped_deadline")
    return min(values) if values else None


def request_timeout(metadata):
    """Reject unmetered scoped deadlines; return the ordinary request timeout."""
    if (metadata or {}).get("strict_completion") is True and current_budget() is None:
        raise BudgetExhausted("strict_completion_requires_budget")
    deadline = scoped_deadline(metadata)
    if deadline is not None:
        if current_budget() is None:
            raise BudgetExhausted("scoped_deadline_requires_budget")
        if deadline <= time.time():
            raise BudgetExhausted("scoped_deadline_exhausted")
    return (metadata or {}).get("timeout_seconds")

class RunBudgetLedger:
    """One SQLite row per Run, updated under BEGIN IMMEDIATE across workers."""

    def __init__(self, connection=None, lock=None, *, database_path=":memory:"):
        self.owns_connection = connection is None
        self.connection = connection or sqlite3.connect(str(database_path), check_same_thread=False)
        self.lock = lock or threading.RLock()
        self._closed = False
        self.database_path = self.connection.execute("PRAGMA database_list").fetchone()[2]
        self.late_usage_evidence_dir = None
        with self.lock:
            self.connection.execute(
                "CREATE TABLE IF NOT EXISTS run_budgets (run_id TEXT PRIMARY KEY, ledger_json TEXT NOT NULL)"
            )
            self.connection.commit()

    def close(self):
        with self.lock:
            if not self._closed and self.owns_connection:
                self.connection.close()
            self._closed = True

    @contextmanager
    def _transaction(self, run_id):
        with self.lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                row = self.connection.execute(
                    "SELECT ledger_json FROM run_budgets WHERE run_id=?", (run_id,)
                ).fetchone()
                state = json.loads(row[0]) if row else None
                yield state
                if state is not None:
                    self.connection.execute(
                        "UPDATE run_budgets SET ledger_json=? WHERE run_id=?",
                        (json.dumps(state), run_id),
                    )
                self.connection.commit()
            except BaseException:
                self.connection.rollback()
                raise

    def ensure(self, run_id, limits, *, deadline_at=None):
        if deadline_at is not None and (type(deadline_at) not in {int, float} or not math.isfinite(deadline_at)):
            raise ValueError("run_budget_deadline_invalid")
        with self._transaction(run_id) as state:
            if state is None:
                now = time.time()
                state = {
                    "limits": asdict(limits),
                    "started_at": now,
                    "deadline_at": min(now + limits.max_runtime_seconds, deadline_at)
                    if deadline_at is not None else now + limits.max_runtime_seconds,
                    "actions": [],
                }
                self.connection.execute(
                    "INSERT INTO run_budgets VALUES (?,?)", (run_id, json.dumps(state))
                )
        return RunBudget(self, run_id)

    def reserve(
        self,
        run_id,
        kind,
        *,
        logical_call_id=None,
        attempt_id=None,
        input_estimate=0,
        output_cap=0,
        role=None,
        tool_call_id=None,
        attempt_event=None,
        solver_call_id=None,
    ):
        if kind not in {"logical", "http", "tool"}:
            raise ValueError("run_budget_kind_invalid")
        if any(type(value) is not int or value < 0 for value in (input_estimate, output_cap)):
            raise ValueError("run_budget_reservation_invalid")
        with self._transaction(run_id) as state:
            if state is None:
                raise BudgetExhausted("budget_uninitialized")
            assert_dispatch_allowed(self.connection, run_id)
            summary = _summary(state)
            limits = state["limits"]
            if time.time() >= state["deadline_at"]:
                raise BudgetExhausted("run_deadline_exhausted")
            if kind == "logical":
                if summary["logical_calls"] >= limits["max_model_calls"]:
                    raise BudgetExhausted("run_model_budget_exhausted")
            elif kind == "http":
                if (
                    summary["http_attempts"] >= limits["max_http_attempts"]
                    or summary["charged_tokens"] + input_estimate + output_cap
                    > limits["max_tokens"]
                ):
                    raise BudgetExhausted("run_model_budget_exhausted")
            elif kind == "tool" and summary["tool_calls"] >= limits["max_tool_calls"]:
                raise BudgetExhausted("run_tool_budget_exhausted")
            action_id = attempt_id or uuid4().hex
            state["actions"].append(
                {
                    "id": action_id,
                    "kind": kind,
                    "logical_call_id": logical_call_id,
                    "solver_call_id": solver_call_id,
                    "role": role,
                    "tool_call_id": tool_call_id,
                    "input_estimate": input_estimate,
                    "output_cap": output_cap,
                    "public_attempt": ({**public_attempt(attempt_event, run_id=run_id, role=role), "started_at_utc": attempt_event.get("started_at_utc"), "dispatch_status": "reserved_dispatch_unconfirmed", "solver_call_id": public_solver_call_id(run_id, solver_call_id)} if attempt_event is not None else None),
                    "status": "reserved",
                    "usage": provider_usage(None),
                }
            )
            return action_id, max(0.001, state["deadline_at"] - time.time())

    def settle(self, run_id, action_id, event):
        with self.lock:
            if self._closed:
                from .run_budget_late import settle_closed
                return settle_closed(self, run_id, action_id, event)
            return self._settle_open(run_id, action_id, event)

    def _settle_open(self, run_id, action_id, event):
        with self._transaction(run_id) as state:
            for action in state["actions"]:
                if action["id"] == action_id:
                    if (action["kind"] == "http" and action["status"] == "success"
                            and all(action["usage"][key] is not None for key in ("prompt_tokens", "completion_tokens", "total_tokens"))):
                        break
                    usage = provider_usage(event)
                    if action["kind"] == "http":
                        if any(previous is not None and usage[key] is not None and previous != usage[key]
                               for key, previous in action["usage"].items()):
                            break  # Conflicting evidence cannot release an unknown reservation.
                        usage = {key: previous if previous is not None else usage[key]
                                 for key, previous in action["usage"].items()}
                        if action["status"] == "success" and usage == action["usage"]:
                            break
                        previous_attempt = action.get("public_attempt") or {}
                        if (action["status"] == "unknown" and event.get("status") == "error"
                                and event.get("error_category") == "timeout"):
                            # A later local timeout cannot make an unfinished remote reply known.
                            event = {**event, **previous_attempt, "status": "unknown"}
                        if action["status"] == "success" and event.get("status") != "success":
                            break  # A later failed observation cannot undo a confirmed result.
                        projection = public_attempt({**event, "usage": usage}, run_id=run_id, role=action["role"])
                        projection["deadline_at"] = previous_attempt.get("deadline_at") or projection["deadline_at"]
                        if event.get("status") == "not_submitted":
                            dispatch_status = "not_submitted"
                        elif (event.get("error_category") == "timeout"
                              and event.get("http_status") is None
                              and event.get("response_headers_seconds") is None):
                            dispatch_status = "reserved_dispatch_unconfirmed"
                        else:
                            dispatch_status = "transport_observed"
                        action["public_attempt"] = {**projection, "started_at_utc": previous_attempt.get("started_at_utc") or event.get("started_at_utc"), "dispatch_status": dispatch_status, "solver_call_id": public_solver_call_id(run_id, action.get("solver_call_id"))}
                    action.update(
                        status=event.get("status", "unknown"),
                        usage=usage,
                        duration_seconds=event.get("duration_seconds"),
                    )
                    return True
            return False

    def _read_row(self, run_id):
        if self.lock.acquire(blocking=False):
            try:
                return self.connection.execute(
                    "SELECT ledger_json FROM run_budgets WHERE run_id=?", (run_id,)
                ).fetchone()
            finally:
                self.lock.release()
        if self.database_path:
            uri = Path(self.database_path).resolve().as_uri() + "?mode=ro"
            reader = sqlite3.connect(uri, uri=True, timeout=1)
            try:
                return reader.execute(
                    "SELECT ledger_json FROM run_budgets WHERE run_id=?", (run_id,)
                ).fetchone()
            finally:
                reader.close()
        with self.lock:
            return self.connection.execute(
                "SELECT ledger_json FROM run_budgets WHERE run_id=?", (run_id,)
            ).fetchone()

    def view(self, run_id):
        """Read budget and attempts from the same persisted ledger version."""
        row = self._read_row(run_id)
        if row is None:
            return None, []
        state = json.loads(row[0])
        return _summary(state), [a["public_attempt"] for a in state["actions"]
                                 if a.get("public_attempt")]
    def attempts(self, run_id):
        return self.view(run_id)[1]

    def snapshot(self, run_id):
        row = self._read_row(run_id)
        return _summary(json.loads(row[0])) if row is not None else None


class RunBudget:
    def __init__(self, ledger, run_id):
        self.ledger, self.run_id = ledger, run_id

    def model_call(self, role=None, *, solver_call_id=None, deadline_at=None, strict_completion=False):
        if deadline_at is not None and deadline_at <= time.time():
            raise BudgetExhausted("scoped_deadline_exhausted")
        action_id, _remaining = self.ledger.reserve(self.run_id, "logical", role=role, solver_call_id=solver_call_id)
        return ModelCallBudget(self.ledger, self.run_id, action_id, role, solver_call_id, deadline_at, strict_completion)

    def before_attempt(self, event, input_estimate):
        check_control()
        return self.ledger.reserve(
            self.run_id,
            "http",
            logical_call_id=event["logical_call_id"],
            attempt_id=event["attempt_id"],
            input_estimate=input_estimate,
            output_cap=event["max_tokens"],
            role=event.get("role"),
            attempt_event=event,
            solver_call_id=event.get("solver_call_id"),
        )[1]

    def after_attempt(self, event):
        self.ledger.settle(self.run_id, event["attempt_id"], event)

    def snapshot(self):
        return self.ledger.snapshot(self.run_id)

    def remaining_seconds(self):
        return max(0.001, self.snapshot()["deadline_at"] - time.time())


class ModelCallBudget(RunBudget):
    def __init__(self, ledger, run_id, logical_call_id, role, solver_call_id=None, deadline_at=None, strict_completion=False):
        super().__init__(ledger, run_id)
        self.logical_call_id, self.role = logical_call_id, role
        self.solver_call_id = solver_call_id
        self.deadline_at = deadline_at
        self.strict_completion = strict_completion

    def remaining_seconds(self):
        remaining = super().remaining_seconds()
        return min(remaining, max(0, self.deadline_at - time.time())) if self.deadline_at is not None else remaining

    def before_attempt(self, event, input_estimate):
        if self.deadline_at is not None and self.deadline_at <= time.time():
            raise BudgetExhausted("scoped_deadline_exhausted")
        event["logical_call_id"] = self.logical_call_id
        event["role"] = self.role
        event["solver_call_id"] = self.solver_call_id
        return super().before_attempt(event, input_estimate)


def _summary(state):
    # Known counters sum only fields actually returned by the provider. Missing
    # fields retain their reservation even when a total-only usage is available.
    attempts = [a for a in state["actions"] if a["kind"] == "http"]
    fields = ("prompt_tokens", "completion_tokens", "total_tokens")
    known = {field: sum(a["usage"][field] or 0 for a in attempts) for field in fields}
    missing = {field: sum(a["usage"][field] is None for a in attempts) for field in fields}
    charged = reserved = 0
    for action in attempts:
        usage = action["usage"]
        held = (action["input_estimate"] if usage["prompt_tokens"] is None else 0) + (
            action["output_cap"] if usage["completion_tokens"] is None else 0
        )
        attempt = action.get("public_attempt") or {}
        if (action["status"] == "unknown" or (action["status"] == "error"
                and (attempt.get("error_category") in {"timeout", "connectivity", "missing_finish_reason", "missing_stream_terminal"}
                     or (attempt.get("error_category") == "http_status"
                         and 500 <= (attempt.get("http_status") or 0) < 600)))):
            held = action["input_estimate"] + action["output_cap"]
            # The known counts are already inside the full original reservation.
            accounted = max(action["input_estimate"], usage["prompt_tokens"] or 0) + max(
                action["output_cap"], usage["completion_tokens"] or 0)
        else:
            accounted = held + (usage["prompt_tokens"] or 0) + (usage["completion_tokens"] or 0)
        reserved += held
        charged += max(usage["total_tokens"] or 0, accounted)
    return {
        "limits": state["limits"],
        "logical_calls": sum(a["kind"] == "logical" for a in state["actions"]),
        "http_attempts": len(attempts),
        "tool_calls": sum(a["kind"] == "tool" for a in state["actions"]),
        "provider_known": {
            field: None if attempts and missing[field] == len(attempts) else value
            for field, value in known.items()
        },
        "provider_unknown_fields": missing,
        "reserved_tokens": reserved,
        "charged_tokens": charged,
        "local_input_estimate": sum(a["input_estimate"] for a in attempts),
        "estimate_source": "local_utf8_bytes",
        "unknown_attempts": sum(
            any(a["usage"][field] is None for field in fields) for a in attempts
        ),
        "unresolved_attempts": sum(
            a["status"] in {"reserved", "pending", "error", "unknown"} for a in attempts
        ),
        "tool_wall_time_seconds": sum(
            a.get("duration_seconds") or 0 for a in state["actions"] if a["kind"] == "tool"
        ),
        "unknown_tool_calls": sum(
            a["kind"] == "tool" and a["status"] in {"reserved", "unknown", "timeout"}
            for a in state["actions"]
        ),
        "started_at": state["started_at"],
        "deadline_at": state["deadline_at"],
        "ended_at": state.get("ended_at"),
        "wall_time_seconds": max(0, state.get("ended_at", time.time()) - state["started_at"]),
        "cost": None,
    }


_current: ContextVar[Any] = ContextVar("showcase_run_budget", default=None)


def current_budget():
    return _current.get()


@contextmanager
def bind_budget(budget):
    token = _current.set(budget)
    try:
        yield budget
    finally:
        _current.reset(token)


def budgeted_tool(function):
    """Apply the current Run ledger to every registry path, including graph nodes."""

    @wraps(function)
    @controlled_action
    def invoke(self, name, arguments, **kwargs):
        budget = current_budget()
        if budget is None:
            return function(self, name, arguments, **kwargs)
        action_id, _remaining = budget.ledger.reserve(
            budget.run_id, "tool", role=name, tool_call_id=kwargs.get("tool_call_id")
        )
        started = time.monotonic()
        try:
            result = function(self, name, arguments, **kwargs)
        except BaseException:
            budget.ledger.settle(budget.run_id, action_id, {"status": "unknown"})
            raise
        budget.ledger.settle(
            budget.run_id,
            action_id,
            {
                "status": result.status,
                "duration_seconds": time.monotonic() - started,
            },
        )
        return result

    return invoke


def execute_graph(ledger, limits, loop, state, *, run_id, resume=False):
    """Use the same ledger when the accepted LangGraph control seam executes."""
    with bind_budget(ledger.ensure(run_id, limits)) as budget:
        execute = loop.resume if resume else loop.run
        result = execute(state, thread_id=run_id)
        result["budget"] = budget.snapshot()
        return result


def freeze_budget(connection, run_id):
    """Freeze elapsed Run execution in the caller's terminal transaction."""
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='run_budgets'").fetchone():
        return
    connection.execute(
        "UPDATE run_budgets SET ledger_json=json_set(ledger_json,'$.ended_at',?) "
        "WHERE run_id=? AND json_extract(ledger_json,'$.ended_at') IS NULL",
        (time.time(), run_id),
    )
    row = connection.execute("SELECT ledger_json FROM run_budgets WHERE run_id=?", (run_id,)).fetchone()
    return _summary(json.loads(row[0])) if row is not None else None
