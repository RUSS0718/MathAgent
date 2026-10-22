"""Persistence for Solver Harness state in the Showcase SQLite connection."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

_SOLVER_STORAGE_LOCK = threading.RLock()


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
            with _SOLVER_STORAGE_LOCK, self._connection:
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
    ) -> dict[str, Any]:
        """Atomically compare-and-swap the snapshot and append one event."""

        connection = self._connection
        with _SOLVER_STORAGE_LOCK:
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
                    SELECT state_json, state_revision
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
                result = self._read_run(run_id)
                if result is None:
                    raise SolverPersistenceError("commit_event")
                connection.commit()
                return result
            except (SolverRevisionConflictError, SolverEventConflictError):
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
            state = json.loads(row["state_json"])
            if (
                not isinstance(state, dict)
                or state.get("run_id") != run_id
                or state.get("problem_hash") != row["problem_hash"]
                or state.get("config_hash") != row["config_hash"]
                or state.get("state_revision") != row["state_revision"]
            ):
                raise SolverPersistenceError("get_run")
            event_rows = self._connection.execute(
                """
                SELECT event_json FROM solver_events
                WHERE run_id = ? ORDER BY sequence
                """,
                (run_id,),
            ).fetchall()
            events = [json.loads(item["event_json"]) for item in event_rows]
            if any(
                not isinstance(event, dict) or event.get("run_id") != run_id for event in events
            ):
                raise SolverPersistenceError("get_run")
            for event in events:
                event.pop("_request_hash", None)
        except SolverPersistenceError:
            raise
        except (sqlite3.Error, TypeError, ValueError) as exc:
            raise SolverPersistenceError("get_run") from exc
        return {
            "run_id": run_id,
            "state": state,
            "events": events,
            "state_revision": int(row["state_revision"]),
        }


def _json(value: Mapping[str, Any]) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise SolverPersistenceError("serialize") from exc
