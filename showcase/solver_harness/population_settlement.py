"""Reconcile physical usage after a delayed or interrupted settlement callback."""

import json
import sqlite3
from types import SimpleNamespace


def reconcile_database(database_path, run_id):
    """Attempt repair without delaying the independent public snapshot reader."""
    from .storage import _SOLVER_STORAGE_LOCK

    if not _SOLVER_STORAGE_LOCK.acquire(blocking=False):
        return
    connection = None
    try:
        connection = sqlite3.connect(database_path, timeout=0)
        connection.row_factory = sqlite3.Row
        reconcile_settlement(connection, run_id)
    except sqlite3.OperationalError as exc:
        if getattr(exc, "sqlite_errorcode", None) not in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
            raise
    finally:
        if connection is not None:
            connection.close()
        _SOLVER_STORAGE_LOCK.release()


def reconcile_settlement(connection, run_id):
    """Repair only settlement, leaving unknown mathematical results untouched."""
    if connection.in_transaction:
        return
    row = connection.execute("SELECT state_json FROM solver_states WHERE run_id=?", (run_id,)).fetchone()
    if row is None:
        return
    state = json.loads(row[0])
    if state.get("population_policy", {}).get("enabled") is not True:
        return
    from .population_store import command
    from .storage import SolverStateStore

    harness = SimpleNamespace(_state_store=SolverStateStore(connection),
                              _population_owner=None, _event_observer=None)
    for action in state.get("population", {}).get("actions", {}).values():
        if action.get("status") != "unknown" or action.get("settlement_status") != "pending":
            continue
        try:
            command(harness, run_id, "physical_settlement", action_id=action["action_id"])
        except sqlite3.OperationalError as exc:
            if getattr(exc, "sqlite_errorcode", None) not in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
                raise
            return
