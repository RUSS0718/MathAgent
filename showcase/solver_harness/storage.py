"""Persistence for Solver Harness state in the Showcase SQLite connection."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from ..run_budget import public_solver_call_id
from ..run_control import RunStopped
from .product_control import controlled_patch

_SOLVER_STORAGE_LOCK = threading.RLock()


class _PublicCallLookup(dict):
    """Keep persisted call keys private while accepting their public aliases."""

    def __init__(self, run_id: str, records: Mapping[str, Any]) -> None:
        super().__init__(records)
        self._run_id = run_id

    def _resolve(self, key: str) -> str:
        if dict.__contains__(self, key):
            return key
        if isinstance(key, str) and key.startswith("solver_call_"):
            matches = [
                call_id for call_id in dict.__iter__(self)
                if public_solver_call_id(self._run_id, call_id) == key
            ]
            if len(matches) == 1:
                return matches[0]
        return key

    def __getitem__(self, key: str) -> Any:
        return dict.__getitem__(self, self._resolve(key))

    def get(self, key: str, default: Any = None) -> Any:
        return dict.get(self, self._resolve(key), default)

    def __contains__(self, key: object) -> bool:
        return dict.__contains__(self, self._resolve(key)) if isinstance(key, str) else False


class SolverPersistenceError(RuntimeError):
    """Raised when a Solver Run snapshot or event cannot be read or written."""

    def __init__(self, operation: str) -> None:
        super().__init__(f"solver_persistence_error: {operation}")
        self.operation = operation


class SolverRevisionConflictError(RuntimeError):
    """Raised when a commit is based on a stale Solver Run revision."""

    def __init__(self, run_id: str, expected_revision: int, current_revision: int) -> None:
        super().__init__(
            "solver_revision_conflict: "
            f"run_id={run_id}, expected={expected_revision}, current={current_revision}"
        )
        self.run_id = run_id
        self.expected_revision = expected_revision
        self.current_revision = current_revision


class SolverEventConflictError(RuntimeError):
    """Raised when an event ID is replayed with a different request payload."""

    def __init__(self, run_id: str, event_id: str) -> None:
        super().__init__(f"solver_event_conflict: event_id already has a different payload: {run_id}/{event_id}")
        self.run_id = run_id
        self.event_id = event_id


class SolverStateStore:
    """Store Solver snapshots and events using the existing Showcase connection."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create_run(self, state: Mapping[str, Any], event: Mapping[str, Any]) -> bool:
        """Atomically create the initial snapshot and event, if the Run is new."""

        run_id = state["run_id"]
        try:
            state = dict(state)
            event = dict(event)
            with _SOLVER_STORAGE_LOCK, self._connection:
                if state.get("route_policy", {}).get("enabled") is True:
                    from .route_budget import derive_route_budget

                    state["route_budget"] = derive_route_budget(self._connection, run_id)
                if state.get("proof_graph_policy", {}).get("enabled") is True:
                    from .proof_graph import evolve_proof_graph

                    graph_patch, graph_summary = evolve_proof_graph(state, event)
                    if graph_patch is not None:
                        state["proof_graph"] = graph_patch
                        event["proof_graph"] = graph_summary
                cursor = self._connection.execute(
                    """
                    INSERT INTO solver_states(
                        run_id, state_json, problem_hash, config_hash, state_revision,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id) DO NOTHING
                    """,
                    (
                        run_id,
                        _json(state),
                        state["problem_hash"],
                        state["config_hash"],
                        state["state_revision"],
                        state["created_at"],
                        state["updated_at"],
                    ),
                )
                if cursor.rowcount == 0:
                    return False
                self._connection.execute(
                    """
                    INSERT INTO solver_events(
                        run_id, sequence, event_id, state_revision, event_json, created_at
                    ) VALUES (?, 1, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        event["event_id"],
                        event["state_revision"],
                        _json(event),
                        event["created_at"],
                    ),
                )
                if state.get("proof_graph_policy", {}).get("enabled") is True:
                    graph_event = {
                        "run_id": run_id,
                        "sequence": 2,
                        "event_id": "proof-graph-bootstrap-v1",
                        "state_revision": state["state_revision"],
                        "event_json": _json({
                            "run_id": run_id,
                            "sequence": 2,
                            "event_id": "proof-graph-bootstrap-v1",
                            "state_revision": state["state_revision"],
                            "type": "proof_graph_bootstrapped",
                            "graph_version": state["proof_graph"]["current_version"],
                            "imported_count": len(state["proof_graph"]["snapshots"][-1]["derivations"]),
                            "not_imported_count": len(state["proof_graph"]["snapshots"][-1]["not_imported_records"]),
                            "created_at": event["created_at"],
                        }),
                        "created_at": event["created_at"],
                    }
                    self._connection.execute(
                        """
                        INSERT INTO solver_events(
                            run_id, sequence, event_id, state_revision, event_json, created_at
                        ) VALUES (:run_id, :sequence, :event_id, :state_revision, :event_json, :created_at)
                        """,
                        graph_event,
                    )
        except (sqlite3.Error, KeyError, TypeError, ValueError) as exc:
            raise SolverPersistenceError("create_run") from exc
        return True

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Return one snapshot and its events, validating their shared identity."""

        with _SOLVER_STORAGE_LOCK:
            owns_transaction = not self._connection.in_transaction
            try:
                if owns_transaction:
                    self._connection.execute("BEGIN")
                result = self._read_run(run_id)
                if owns_transaction:
                    self._connection.commit()
                return result
            except SolverPersistenceError:
                if owns_transaction:
                    self._connection.rollback()
                raise
            except sqlite3.Error as exc:
                if owns_transaction:
                    self._connection.rollback()
                raise SolverPersistenceError("get_run") from exc

    def commit_event(
        self,
        run_id: str,
        *,
        expected_revision: int,
        state_updates: Mapping[str, Any],
        event: Mapping[str, Any],
        request_hash: str,
        validated_run: Mapping[str, Any] | None = None,
        route_authorized: bool = False,
    ) -> dict[str, Any]:
        """Compare-and-swap one event, reusing a matching validated history when supplied."""

        connection = self._connection
        with _SOLVER_STORAGE_LOCK:
            if {"proof_graph", "proof_graph_policy"} & state_updates.keys():
                raise SolverPersistenceError("graph_fields_are_storage_managed")
            if connection.in_transaction:
                raise SolverPersistenceError("commit_event")
            try:
                connection.execute("BEGIN IMMEDIATE")
                prior = connection.execute(
                    """
                    SELECT event_json FROM solver_events
                    WHERE run_id = ? AND event_id = ?
                    """,
                    (run_id, event["event_id"]),
                ).fetchone()
                if prior is not None:
                    saved_event = json.loads(prior["event_json"])
                    if saved_event.get("_request_hash") != request_hash:
                        raise SolverEventConflictError(run_id, event["event_id"])
                    current = self._read_run(run_id)
                    if current is None:
                        raise SolverPersistenceError("commit_event")
                    connection.commit()
                    return current

                row = connection.execute(
                    """
                    SELECT state_json, problem_hash, config_hash, state_revision
                    FROM solver_states WHERE run_id = ?
                    """,
                    (run_id,),
                ).fetchone()
                if row is None:
                    raise SolverPersistenceError("commit_event")
                current_revision = int(row["state_revision"])
                if current_revision != expected_revision:
                    raise SolverRevisionConflictError(
                        run_id, expected_revision, current_revision
                    )

                state = json.loads(row["state_json"])
                if not isinstance(state, dict):
                    raise SolverPersistenceError("commit_event")
                state_updates = controlled_patch(connection, run_id, event, state_updates)
                if route_authorized or any(
                    key in state_updates
                    for key in {
                        "route_registry", "route_lineage", "route_evaluations",
                        "aprs_decisions", "route_invalidations", "active_route_id",
                        "route_budget",
                    }
                ):
                    from .routes import validate_route_state_patch

                    try:
                        validate_route_state_patch(
                            state, event, state_updates, authorized=route_authorized
                        )
                    except ValueError as exc:
                        raise SolverPersistenceError(str(exc)) from exc
                graph_candidate = dict(state)
                graph_candidate.update(state_updates)
                graph_candidate["proof_graph"] = state.get("proof_graph")
                graph_candidate["proof_graph_policy"] = state.get("proof_graph_policy")
                if (graph_candidate.get("proof_graph_policy") or {}).get("enabled") is True:
                    from .proof_graph import evolve_proof_graph

                    receipt_rows = connection.execute(
                        "SELECT event_json FROM solver_events WHERE run_id = ? ORDER BY sequence",
                        (run_id,),
                    ).fetchall()
                    persisted_receipts = {}
                    for receipt_row in receipt_rows:
                        saved = json.loads(receipt_row["event_json"])
                        receipt = saved.get("receipt")
                        if (saved.get("type") == "tool_receipt" and isinstance(receipt, Mapping)
                                and isinstance(receipt.get("receipt_id"), str)):
                            persisted_receipts[receipt["receipt_id"]] = receipt
                    graph_patch, graph_summary = evolve_proof_graph(
                        graph_candidate, event, persisted_receipts
                    )
                    if graph_patch is not None:
                        state_updates = {**state_updates, "proof_graph": graph_patch}
                        event = {**event, "proof_graph": graph_summary}
                        if graph_candidate.get("route_policy", {}).get("enabled") is True:
                            from .routes import invalidate_routes

                            route_patch = invalidate_routes(
                                graph_candidate, graph_patch.get("current_version")
                            )
                            if route_patch:
                                state_updates = {**state_updates, **route_patch}
                                event = {**event, "route_invalidation": route_patch["route_invalidations"][-1]}
                    # The fixed deadline may pass while the derived graph is built.
                    guarded_updates = controlled_patch(connection, run_id, event, state_updates)
                    if guarded_updates != state_updates:
                        state_updates = guarded_updates
                        event = {key: value for key, value in event.items() if key != "proof_graph"}
                if state.get("route_policy", {}).get("enabled") is True:
                    from .route_budget import derive_route_budget
                    from .route_commits import rating_patch, rating_required, terminal_route_patch

                    candidate = {**state, **state_updates}
                    candidate["route_budget"] = derive_route_budget(
                        connection, run_id, candidate.get("route_budget")
                    )
                    if candidate.get("phase") == "TERMINAL":
                        terminal_patch = terminal_route_patch(run_id, candidate)
                        candidate.update(terminal_patch)
                        state_updates = {**state_updates, **terminal_patch}
                        if terminal_patch:
                            event = {**event, "route_terminal": True}
                    if rating_required(state, candidate):
                        derived = rating_patch(candidate, current_revision + 1)
                        candidate.update(derived)
                        state_updates = {**state_updates, **derived}
                        event = {**event, "route_rated": True}
                    state_updates = {**state_updates, "route_budget": candidate["route_budget"]}
                next_revision = current_revision + 1
                now = datetime.now(UTC).isoformat()
                state.update(state_updates)
                state["state_revision"] = next_revision
                state["updated_at"] = now
                stored_event = dict(event)
                stored_event.update(
                    {
                        "run_id": run_id,
                        "state_revision": next_revision,
                        "created_at": now,
                        "_request_hash": request_hash,
                    }
                )

                cursor = connection.execute(
                    """
                    UPDATE solver_states
                    SET state_json = ?, state_revision = ?, updated_at = ?
                    WHERE run_id = ? AND state_revision = ?
                    """,
                    (
                        _json(state),
                        next_revision,
                        now,
                        run_id,
                        expected_revision,
                    ),
                )
                if cursor.rowcount != 1:
                    raise SolverRevisionConflictError(
                        run_id, expected_revision, current_revision
                    )
                sequence = connection.execute(
                    """
                    SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence
                    FROM solver_events WHERE run_id = ?
                    """,
                    (run_id,),
                ).fetchone()["sequence"]
                connection.execute(
                    """
                    INSERT INTO solver_events(
                        run_id, sequence, event_id, state_revision, event_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        sequence,
                        stored_event["event_id"],
                        next_revision,
                        _json(stored_event),
                        now,
                    ),
                )
                if validated_run is not None:
                    validated_state = validated_run.get("state")
                    if (
                        validated_run.get("run_id") != run_id
                        or validated_run.get("state_revision") != expected_revision
                        or not isinstance(validated_run.get("events"), list)
                        or not isinstance(validated_state, Mapping)
                        or validated_state.get("run_id") != run_id
                        or validated_state.get("problem_hash") != row["problem_hash"]
                        or validated_state.get("config_hash") != row["config_hash"]
                        or validated_state.get("state_revision") != expected_revision
                    ):
                        raise SolverPersistenceError("commit_event")
                    events = [dict(item) for item in validated_run["events"]]
                    public_event = dict(stored_event)
                    public_event.pop("_request_hash", None)
                    events.append(public_event)
                else:
                    event_rows = connection.execute(
                        """
                        SELECT event_json FROM solver_events
                        WHERE run_id = ? ORDER BY sequence
                        """,
                        (run_id,),
                    ).fetchall()
                    events = [json.loads(item["event_json"]) for item in event_rows]
                result = self._materialize_run(
                    run_id,
                    state,
                    row["problem_hash"],
                    row["config_hash"],
                    next_revision,
                    events,
                    "commit_event",
                )
                if result is None:
                    raise SolverPersistenceError("commit_event")
                connection.commit()
                return result
            except (SolverRevisionConflictError, SolverEventConflictError, RunStopped):
                connection.rollback()
                raise
            except SolverPersistenceError:
                connection.rollback()
                raise
            except (sqlite3.Error, KeyError, TypeError, ValueError) as exc:
                connection.rollback()
                raise SolverPersistenceError("commit_event") from exc

    def _read_run(self, run_id: str) -> dict[str, Any] | None:
        try:
            row = self._connection.execute(
                """
                SELECT state_json, problem_hash, config_hash, state_revision
                FROM solver_states WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
            if row is None:
                return None
            event_rows = self._connection.execute(
                """
                SELECT event_json FROM solver_events
                WHERE run_id = ? ORDER BY sequence
                """,
                (run_id,),
            ).fetchall()
            events = [json.loads(item["event_json"]) for item in event_rows]
            return self._materialize_run(
                run_id,
                json.loads(row["state_json"]),
                row["problem_hash"],
                row["config_hash"],
                row["state_revision"],
                events,
                "get_run",
            )
        except SolverPersistenceError:
            raise
        except (sqlite3.Error, TypeError, ValueError) as exc:
            raise SolverPersistenceError("get_run") from exc

    @staticmethod
    def _materialize_run(
        run_id: str,
        state: Any,
        problem_hash: str,
        config_hash: str,
        state_revision: int,
        events: list[Any],
        operation: str,
    ) -> dict[str, Any]:
        """Build a public Run projection from already-read snapshot data."""

        if (
            not isinstance(state, dict)
            or state.get("run_id") != run_id
            or state.get("problem_hash") != problem_hash
            or state.get("config_hash") != config_hash
            or state.get("state_revision") != state_revision
        ):
            raise SolverPersistenceError(operation)
        if isinstance(state.get("calls"), dict):
            state["calls"] = _PublicCallLookup(run_id, state["calls"])
        if any(not isinstance(event, dict) or event.get("run_id") != run_id for event in events):
            raise SolverPersistenceError(operation)
        for event in events:
            event.pop("_request_hash", None)
        return {
            "run_id": run_id,
            "state": state,
            "events": events,
            "state_revision": int(state_revision),
        }


def _json(value: Mapping[str, Any]) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise SolverPersistenceError("serialize") from exc
