"""Persistence for Solver Harness state in the Showcase SQLite connection."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from typing import Any


class SolverPersistenceError(RuntimeError):
    """Raised when a Solver Run snapshot or event cannot be read or written."""

    def __init__(self, operation: str) -> None:
        super().__init__(f"solver_persistence_error: {operation}")
        self.operation = operation


class SolverStateStore:
    """Store Solver snapshots and events using the existing Showcase connection."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create_run(self, state: Mapping[str, Any], event: Mapping[str, Any]) -> bool:
        """Atomically create the initial snapshot and event, if the Run is new."""

        run_id = state["run_id"]
        try:
            with self._connection:
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
