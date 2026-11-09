"""Atomic persisted Run reservations; provider usage never becomes a local estimate."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import threading
import time
from collections.abc import Mapping
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
    """Pseudonymize every provider-facing call ID before public projection."""
    if not isinstance(solver_call_id, str) or not solver_call_id:
        return None
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

    def __init__(self, connection=None, lock=None, *, database_path=":memory:", connection_lock=None):
        self.owns_connection = connection is None
        self.connection = connection or sqlite3.connect(str(database_path), check_same_thread=False)
        self.lock = threading.RLock() if lock is None else lock
        self.connection_lock = self.lock if connection_lock is None else connection_lock
        self._closed = False
        self.database_path = self.connection.execute("PRAGMA database_list").fetchone()[2]
        self.late_usage_evidence_dir = None
        with self.lock, self.connection_lock:
            self.connection.execute(
                "CREATE TABLE IF NOT EXISTS run_budgets (run_id TEXT PRIMARY KEY, ledger_json TEXT NOT NULL)"
            )
            self.connection.commit()

    def close(self):
        with self.lock, self.connection_lock:
            if not self._closed and self.owns_connection:
                self.connection.close()
            self._closed = True

    @contextmanager
    def _transaction(self, run_id):
        from .run_budget_late import _settlement_timeout, _shared_gate

        timeout = _settlement_timeout.get()
        with _shared_gate(self, timeout=timeout) as admitted:
            if not admitted:
                raise sqlite3.OperationalError("database is locked")
            busy_timeout = self.connection.execute("PRAGMA busy_timeout").fetchone()[0]
            if timeout is not None:
                self.connection.execute(f"PRAGMA busy_timeout = {int(timeout * 1000)}")
            try:
                with self._transaction_open(run_id) as state:
                    yield state
            finally:
                if timeout is not None:
                    self.connection.execute(f"PRAGMA busy_timeout = {busy_timeout}")

    @contextmanager
    def _transaction_open(self, run_id):
        """Update only while both gates are held by the transaction caller."""
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

    def ensure(self, run_id, limits, *, deadline_at=None, stream_timeout_policy=None):
        if deadline_at is not None and (type(deadline_at) not in {int, float} or not math.isfinite(deadline_at)):
            raise ValueError("run_budget_deadline_invalid")
        from .stream_timeout_policy import validate_snapshot

        stream_timeout_policy = validate_snapshot(stream_timeout_policy)
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
                if stream_timeout_policy is not None:
                    state["stream_timeout_policy"] = stream_timeout_policy
                self.connection.execute(
                    "INSERT INTO run_budgets VALUES (?,?)", (run_id, json.dumps(state))
                )
            elif (
                stream_timeout_policy is not None
                and state.get("stream_timeout_policy") != stream_timeout_policy
            ):
                raise ValueError("run_timeout_policy_binding_mismatch")
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
        from .solver_harness.population_budget import current_population_action

        population_scope = current_population_action()
        population_action_id = population_scope[0] if population_scope else None
        with self._transaction(run_id) as state:
            if state is None:
                raise BudgetExhausted("budget_uninitialized")
            if population_scope is not None and kind in {"logical", "http", "tool"}:
                self._assert_population_owner(run_id, population_action_id, population_scope[1])
            assert_dispatch_allowed(self.connection, run_id)
            summary = _summary(state)
            limits = state["limits"]
            population = self._population_state(run_id)
            closing_call = role in {"final_generator", "whole_solution_verifier"}
            floor = (population.get("closing_reserve", {})
                     if population is not None and not closing_call else {})
            if time.time() >= state["deadline_at"]:
                raise BudgetExhausted("run_deadline_exhausted")
            if kind == "http":
                reserved = next((action for action in state["actions"]
                                 if action.get("kind") == "http"
                                 and action.get("status") == "pre_reserved"
                                 and action.get("logical_call_id") == logical_call_id
                                 and (population_action_id is None
                                      or action.get("population_action_id") == population_action_id)), None)
                if reserved is not None:
                    if population_action_id is not None:
                        self._assert_population_owner(run_id, population_action_id, population_scope[1])
                    if input_estimate > reserved["input_estimate"] or output_cap > reserved["output_cap"]:
                        raise BudgetExhausted("finalization_reservation_too_small")
                    action_id = attempt_id or uuid4().hex
                    if any(action.get("id") == action_id for action in state["actions"]):
                        raise BudgetExhausted("run_attempt_identity_conflict")
                    reserved.update(
                        id=action_id,
                        status="reserved",
                        reservation_attempt_id=reserved["id"],
                        attempt_event=attempt_event,
                        public_attempt=(
                            {**public_attempt(attempt_event, run_id=run_id, role=role),
                             "started_at_utc": attempt_event.get("started_at_utc"),
                             "dispatch_status": "reserved_dispatch_unconfirmed",
                             "solver_call_id": public_solver_call_id(run_id, solver_call_id)}
                            if attempt_event is not None else None
                        ),
                    )
                    return action_id, max(0.001, state["deadline_at"] - time.time())
                if population_action_id is not None:
                    raise BudgetExhausted("population_http_reservation_exhausted")
            if kind == "tool" and population_action_id is not None:
                held_tool = next((action for action in state["actions"]
                                  if action.get("kind") == "tool"
                                  and action.get("status") == "pre_reserved"
                                  and action.get("population_action_id") == population_action_id
                                  and action.get("role") in {role, "*"}), None)
                if held_tool is None:
                    raise BudgetExhausted("population_tool_reservation_exhausted")
                action_id = attempt_id or tool_call_id or uuid4().hex
                if any(action.get("id") == action_id for action in state["actions"]):
                    raise BudgetExhausted("run_tool_identity_conflict")
                held_tool.update(id=action_id, role=role, tool_call_id=tool_call_id,
                                 status="reserved")
                return action_id, max(0.001, state["deadline_at"] - time.time())
            if kind == "logical" and population_action_id is not None:
                raise BudgetExhausted("population_model_reservation_exhausted")
            if kind == "logical":
                held = floor.get("model_calls", 0) if population is not None else 0
                if summary["logical_calls"] + 1 + held > limits["max_model_calls"]:
                    raise BudgetExhausted("run_model_budget_exhausted")
            elif kind == "http":
                held_http = floor.get("http_attempts", 0) if population is not None else 0
                held_tokens = floor.get("tokens", 0) if population is not None else 0
                if (
                    summary["http_attempts"] + 1 + held_http > limits["max_http_attempts"]
                    or summary["charged_tokens"] + input_estimate + output_cap + held_tokens
                    > limits["max_tokens"]
                ):
                    raise BudgetExhausted("run_model_budget_exhausted")
            elif kind == "tool" and summary["tool_calls"] + 1 + floor.get("tool_calls", 0) > limits["max_tool_calls"]:
                raise BudgetExhausted("run_tool_budget_exhausted")
            if population is not None and not closing_call and (
                state["deadline_at"] - time.time() < floor.get("time_seconds", 0)
            ):
                raise BudgetExhausted("population_closing_time_reserve_unavailable")
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
                    **({"population_action_id": population_action_id}
                       if population_action_id is not None else {}),
                    "public_attempt": ({**public_attempt(attempt_event, run_id=run_id, role=role), "started_at_utc": attempt_event.get("started_at_utc"), "dispatch_status": "reserved_dispatch_unconfirmed", "solver_call_id": public_solver_call_id(run_id, solver_call_id)} if attempt_event is not None else None),
                    "status": "reserved",
                    "usage": provider_usage(None),
                }
            )
            return action_id, max(0.001, state["deadline_at"] - time.time())

    def reserve_finalization_pair(
        self,
        run_id,
        *,
        reservation_id,
        final_input_estimate,
        final_output_cap,
        review_input_estimate,
        review_output_cap,
    ):
        """Atomically hold one generator and one whole-review call in this Run."""
        if not isinstance(reservation_id, str) or not reservation_id.strip():
            raise ValueError("finalization_reservation_id_invalid")
        estimates = (final_input_estimate, final_output_cap,
                     review_input_estimate, review_output_cap)
        if any(type(value) is not int or value < 0 for value in estimates):
            raise ValueError("run_budget_reservation_invalid")
        reservation_id = reservation_id.strip()
        roles = ("final_generator", "whole_solution_verifier")
        with self._transaction(run_id) as state:
            if state is None:
                raise BudgetExhausted("budget_uninitialized")
            assert_dispatch_allowed(self.connection, run_id)
            if time.time() >= state["deadline_at"]:
                raise BudgetExhausted("run_deadline_exhausted")
            existing = [action for action in state["actions"]
                        if action.get("reservation_id") == reservation_id]
            if existing:
                if len(existing) != 4:
                    raise BudgetExhausted("finalization_reservation_incomplete")
                expected = {
                    "final_generator": (final_input_estimate, final_output_cap),
                    "whole_solution_verifier": (review_input_estimate, review_output_cap),
                }
                if any(
                    (action["input_estimate"], action["output_cap"])
                    != expected[action["role"]]
                    for action in existing if action["kind"] == "http"
                ):
                    raise BudgetExhausted("finalization_reservation_conflict")
                return {role: next(action["logical_call_id"] for action in existing
                                   if action["kind"] == "logical" and action["role"] == role)
                        for role in roles}
            summary = _summary(state)
            limits = state["limits"]
            if summary["logical_calls"] + 2 > limits["max_model_calls"]:
                raise BudgetExhausted("run_model_budget_exhausted")
            if summary["http_attempts"] + 2 > limits["max_http_attempts"]:
                raise BudgetExhausted("run_model_budget_exhausted")
            token_reserve = final_input_estimate + final_output_cap + review_input_estimate + review_output_cap
            if summary["charged_tokens"] + token_reserve > limits["max_tokens"]:
                raise BudgetExhausted("run_model_budget_exhausted")
            logical_ids = {}
            for role, input_estimate, output_cap in (
                (roles[0], final_input_estimate, final_output_cap),
                (roles[1], review_input_estimate, review_output_cap),
            ):
                logical_id = f"{reservation_id}:logical:{role}"
                http_id = f"{reservation_id}:http:{role}"
                logical_ids[role] = logical_id
                state["actions"].extend((
                    {
                        "id": logical_id,
                        "kind": "logical",
                        "logical_call_id": logical_id,
                        "solver_call_id": None,
                        "role": role,
                        "tool_call_id": None,
                        "input_estimate": 0,
                        "output_cap": 0,
                        "reservation_id": reservation_id,
                        "status": "pre_reserved",
                        "usage": provider_usage(None),
                    },
                    {
                        "id": http_id,
                        "kind": "http",
                        "logical_call_id": logical_id,
                        "solver_call_id": None,
                        "role": role,
                        "tool_call_id": None,
                        "input_estimate": input_estimate,
                        "output_cap": output_cap,
                        "reservation_id": reservation_id,
                        "status": "pre_reserved",
                        "usage": provider_usage(None),
                    },
                ))
            return logical_ids

    def claim_finalization_call(self, run_id, role, solver_call_id=None):
        """Claim the oldest held logical slot for a closeout role, if one exists."""
        with self._transaction(run_id) as state:
            if state is None:
                raise BudgetExhausted("budget_uninitialized")
            for action in state["actions"]:
                if (action.get("kind") == "logical"
                        and action.get("role") == role
                        and action.get("status") == "pre_reserved"):
                    action["status"] = "reserved"
                    action["solver_call_id"] = solver_call_id
                    for reserved in state["actions"]:
                        if (reserved.get("kind") == "http"
                                and reserved.get("status") == "pre_reserved"
                                and reserved.get("logical_call_id") == action["logical_call_id"]):
                            reserved["solver_call_id"] = solver_call_id
                    return action["logical_call_id"]
        return None

    def claim_population_call(self, run_id, population_action_id, *, role, solver_call_id=None):
        """Claim one model-call slot already held for this specific WorkUnit."""
        from .solver_harness.population_budget import current_population_action

        scope = current_population_action()
        if not scope or scope[0] != population_action_id:
            raise BudgetExhausted("population_action_scope_missing")
        with self._transaction(run_id) as state:
            if state is None:
                raise BudgetExhausted("budget_uninitialized")
            self._assert_population_owner(run_id, population_action_id, scope[1])
            for action in state["actions"]:
                if (action.get("kind") == "logical"
                        and action.get("population_action_id") == population_action_id
                        and action.get("role") == role
                        and action.get("status") == "pre_reserved"):
                    action.update(status="reserved", solver_call_id=solver_call_id)
                    return action["logical_call_id"]
        return None

    def _population_closing_floor(self, run_id):
        population = self._population_state(run_id)
        return dict(population.get("closing_reserve") or {}) if population is not None else {}

    def _population_state(self, run_id):
        row = self.connection.execute(
            "SELECT state_json FROM solver_states WHERE run_id=?", (run_id,)
        ).fetchone()
        if row is None:
            return None
        try:
            state = json.loads(row[0])
            if state.get("population_policy", {}).get("enabled") is not True:
                return None
            return state.get("population", {})
        except (TypeError, ValueError):
            raise BudgetExhausted("population_closing_reserve_unavailable") from None

    def _assert_population_owner(self, run_id, action_id, owner):
        row = self.connection.execute(
            "SELECT state_json FROM solver_states WHERE run_id=?", (run_id,)
        ).fetchone()
        if row is None:
            raise BudgetExhausted("population_owner_epoch_mismatch")
        try:
            state = json.loads(row[0])
            if state.get("population", {}).get("owner") != owner:
                raise BudgetExhausted("population_owner_epoch_mismatch")
            if action_id is None:
                if state.get("phase") == "TERMINAL":
                    raise BudgetExhausted("population_exploration_frozen")
                return
            action = state.get("population", {}).get("actions", {}).get(action_id)
            if state.get("phase") == "TERMINAL" or state.get("population", {}).get("freeze") is not None:
                raise BudgetExhausted("population_exploration_frozen")
            if (state.get("population", {}).get("owner") != owner or action is None
                    or action.get("owner") != owner or action.get("status") != "inflight"):
                raise BudgetExhausted("population_owner_epoch_mismatch")
        except (TypeError, ValueError):
            raise BudgetExhausted("population_owner_epoch_mismatch") from None

    def settle(self, run_id, action_id, event):
        with self.lock:
            if self._closed:
                from .run_budget_late import settle_closed
                return settle_closed(self, run_id, action_id, event)
            settled = self._settle_open(run_id, action_id, event)
        if settled:
            self._settle_population_resource(run_id, action_id)
        return settled

    def _settle_population_resource(self, run_id, attempt_id):
        """Update population settlement after physical usage is committed."""
        if not isinstance(attempt_id, str):
            return
        try:
            with self.connection_lock:
                row = self.connection.execute(
                    "SELECT ledger_json FROM run_budgets WHERE run_id=?", (run_id,)
                ).fetchone()
                if row is None:
                    return
                action = next((item for item in json.loads(row[0])["actions"]
                               if item.get("id") == attempt_id and item.get("kind") == "http"), None)
                population_action_id = action.get("population_action_id") if action else None
                if not isinstance(population_action_id, str):
                    return
                from types import SimpleNamespace

                from .solver_harness.population_store import command
                from .solver_harness.storage import SolverStateStore

                command(SimpleNamespace(
                    _state_store=SolverStateStore(self.connection),
                    _population_owner=None, _event_observer=None,
                ), run_id, "physical_settlement", action_id=population_action_id)
        except sqlite3.OperationalError as exc:
            # Physical usage remains in the budget ledger; a later population
            # read or action outcome can reconcile the separate settlement view.
            if getattr(exc, "sqlite_errorcode", None) not in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
                raise
            return

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
                    if "execution_evidence" in event:
                        action["execution_evidence"] = event["execution_evidence"]
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
                if self.connection_lock.acquire(blocking=False):
                    try:
                        return self.connection.execute(
                            "SELECT ledger_json FROM run_budgets WHERE run_id=?", (run_id,)
                        ).fetchone()
                    finally:
                        self.connection_lock.release()
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
        with self.lock, self.connection_lock:
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

    def stream_timeout_policy(self, run_id):
        """Read the exact stream policy frozen in this Run's durable budget row."""

        row = self._read_row(run_id)
        if row is None:
            return None
        state = json.loads(row[0])
        policy = state.get("stream_timeout_policy")
        return dict(policy) if isinstance(policy, Mapping) else None


class RunBudget:
    def __init__(self, ledger, run_id):
        self.ledger, self.run_id = ledger, run_id

    def model_call(self, role=None, *, solver_call_id=None, deadline_at=None, strict_completion=False):
        if deadline_at is not None and deadline_at <= time.time():
            raise BudgetExhausted("scoped_deadline_exhausted")
        from .solver_harness.population_budget import current_population_action

        scope = current_population_action()
        if scope and scope[0] is not None:
            action_id = self.ledger.claim_population_call(
                self.run_id, scope[0], role=role, solver_call_id=solver_call_id
            )
            if action_id is None:
                raise BudgetExhausted("population_model_reservation_exhausted")
        else:
            action_id = self.ledger.claim_finalization_call(
                self.run_id, role, solver_call_id=solver_call_id
            )
        if action_id is None:
            action_id, _remaining = self.ledger.reserve(
                self.run_id, "logical", role=role, solver_call_id=solver_call_id
            )
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

    def stream_timeout_policy(self):
        """Return the frozen call policy, or ``None`` for legacy Runs."""

        return self.ledger.stream_timeout_policy(self.run_id)

    def absolute_deadline(self):
        """Keep the original UTC deadline; never round-trip through duration clocks."""
        deadline = self.snapshot()["deadline_at"]
        scoped = getattr(self, "deadline_at", None)
        return min(deadline, scoped) if scoped is not None else deadline

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
    http_actions = [a for a in state["actions"] if a["kind"] == "http"]
    attempts = [a for a in http_actions if a.get("status") != "pre_reserved"]
    fields = ("prompt_tokens", "completion_tokens", "total_tokens")
    known = {field: sum(a["usage"][field] or 0 for a in attempts) for field in fields}
    missing = {field: sum(a["usage"][field] is None for a in attempts) for field in fields}
    charged = reserved = 0
    for action in http_actions:
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
        **({"stream_timeout_policy": state["stream_timeout_policy"]}
           if "stream_timeout_policy" in state else {}),
        "logical_calls": sum(a["kind"] == "logical" for a in state["actions"]),
        "http_attempts": len(http_actions),
        "tool_calls": sum(a["kind"] == "tool" for a in state["actions"]),
        "provider_known": {
            field: None if attempts and missing[field] == len(attempts) else value
            for field, value in known.items()
        },
        "provider_unknown_fields": missing,
        "reserved_tokens": reserved,
        "charged_tokens": charged,
        "local_input_estimate": sum(a["input_estimate"] for a in http_actions),
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
            a["kind"] == "tool"
            and (
                a["status"] in {"reserved", "unknown"}
                or (a.get("execution_evidence") or {}).get("unknown_outcome") is True
                or (
                    a["status"] == "timeout"
                    and not (
                        (a.get("execution_evidence") or {}).get("unknown_outcome") is False
                        and (a.get("execution_evidence") or {}).get("cleanup_verified") is True
                    )
                )
            )
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
        from .solver_harness.population_budget import current_population_action

        scope = current_population_action()
        if scope and scope[0] is not None:
            raise BudgetExhausted("population_tool_reservation_unavailable")
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
            _tool_settlement(result, time.monotonic() - started),
        )
        return result

    return invoke


def _tool_settlement(result, duration_seconds):
    """Settle a tool action while retaining only safe executor outcome evidence."""
    settlement = {"status": result.status, "duration_seconds": duration_seconds}
    value = getattr(result, "value", None)
    if isinstance(value, Mapping):
        evidence = {
            key: value[key]
            for key in ("unknown_outcome", "cleanup_verified", "executed", "timeout")
            if type(value.get(key)) is bool
        }
        if evidence:
            settlement["execution_evidence"] = evidence
    return settlement


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
