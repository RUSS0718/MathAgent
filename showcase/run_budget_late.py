"""Late usage settlement reopens only the original S3 database, never dispatch."""
import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from uuid import uuid4

from llm_response import USAGE_FIELDS, provider_usage, safe_identifier

_ERROR_CATEGORIES = {"timeout", "connectivity", "missing_finish_reason", "missing_stream_terminal",
                     "invalid_response", "http_status"}
_settlement_timeout = ContextVar("settlement_timeout", default=None)


@contextmanager
def _shared_gate(ledger, *, blocking=True, timeout=None):
    """Acquire the ledger and SQLite-owner locks in transaction order.

    A timeout settlement must admit both locks before touching the shared
    connection.  Acquiring only ``ledger.lock`` leaves the following
    ``connection_lock`` acquisition unbounded when the Workspace owner is
    writing the same connection.
    """
    locks = [ledger.lock]
    if ledger.connection_lock is not ledger.lock:
        locks.append(ledger.connection_lock)
    acquired = []
    deadline = time.monotonic() + timeout if timeout is not None else None
    try:
        for lock in locks:
            if not blocking:
                admitted = lock.acquire(blocking=False)
            elif deadline is None:
                admitted = lock.acquire()
            else:
                admitted = lock.acquire(timeout=max(0.0, deadline - time.monotonic()))
            if not admitted:
                yield False
                return
            acquired.append(lock)
        yield True
    finally:
        for lock in reversed(acquired):
            lock.release()


def _database_identity(ledger):
    if not ledger.database_path:
        return None
    path = os.path.normcase(os.path.realpath(ledger.database_path))
    return hashlib.sha256(path.encode("utf-8")).hexdigest()


def _save_unresolved(ledger, run_id, event):
    """Publish observation evidence, not a settlement receipt. No auto-replay."""
    logger = logging.getLogger(__name__)
    logger.warning("late settlement unresolved: run_id=%s attempt_id=%s",
                   safe_identifier(run_id), safe_identifier(event.get("attempt_id")))
    directory = ledger.late_usage_evidence_dir
    if directory is None:
        if not ledger.database_path:
            logger.warning("late settlement unresolved; evidence unavailable: no durable location")
            return
        directory = str(ledger.database_path) + ".late-usage"
    temporary = None
    try:
        run_id, attempt_id = safe_identifier(run_id), safe_identifier(event.get("attempt_id"))
        if run_id is None or attempt_id is None:
            raise ValueError("invalid identity")
        status = event.get("status")
        status = status if status in {"success", "error", "unknown"} else "unknown"
        category = event.get("error_category")
        if status == "error" and category not in _ERROR_CATEGORIES:
            status = "unknown"  # An unrecognized failure must retain the reservation.
        http_status = event.get("http_status")
        record = dict(version=1, database_id=_database_identity(ledger), run_id=run_id,
                      attempt_id=attempt_id, observed_at=time.time(), status=status,
                      error_category=category if category in _ERROR_CATEGORIES else None,
                      http_status=http_status if type(http_status) is int and 100 <= http_status <= 599 else None,
                      usage=provider_usage(event))
        # Keep pending observations separate from legacy successful supplemental archives.
        directory = Path(directory) / "pending"
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / (uuid4().hex + ".json")
        temporary = target.with_suffix(".tmp")
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(record, stream, sort_keys=True, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except (OSError, ValueError, TypeError):
        logger.warning("late settlement unresolved; evidence write failed")
    else:
        if ledger.database_path:
            logger.warning("late settlement unresolved; evidence saved for explicit reconciliation")
        else:
            logger.warning("late settlement unresolved; evidence saved; in-memory ledger cannot be recovered")
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                logger.warning("late evidence temporary cleanup failed")


def reconcile_late_evidence(ledger, evidence_path):
    """Replay one trusted local observation against its original file DB only.

    Returns the ledger's changed flag, not a claim of complete metering. Keeps
    evidence for audit/replay; never creates runs, reservations or model calls.
    Memory DB observations cannot be recovered after restart. Moving a DB also
    requires operator review because evidence is bound to its original path.
    """
    with Path(evidence_path).open(encoding="utf-8") as stream:
        record = json.loads(stream.read(16385))
    if (not isinstance(record, dict) or record.get("version") != 1 or not ledger.database_path
            or record.get("database_id") != _database_identity(ledger)):
        raise ValueError("evidence does not identify this file database")
    run_id, attempt_id = record.get("run_id"), record.get("attempt_id")
    if not safe_identifier(run_id) or not safe_identifier(attempt_id):
        raise ValueError("invalid evidence identity")
    status, category, http_status = record.get("status"), record.get("error_category"), record.get("http_status")
    if (status not in {"success", "error", "unknown"}
            or category is not None and category not in _ERROR_CATEGORIES
            or status == "error" and category is None
            or http_status is not None and (type(http_status) is not int or not 100 <= http_status <= 599)):
        raise ValueError("invalid evidence outcome")
    usage = record.get("usage")
    if (not isinstance(usage, dict) or set(usage) != set(USAGE_FIELDS)
            or any(value is not None and (type(value) is not int or value < 0) for value in usage.values())):
        raise ValueError("invalid evidence usage")
    event = dict(attempt_id=attempt_id, status=status, error_category=category, http_status=http_status,
                 **{key: usage.get(key) for key in ("prompt_tokens", "completion_tokens", "total_tokens")},
                 completion_tokens_details={"reasoning_tokens": usage.get("reasoning_tokens")},
                 prompt_tokens_details={"cached_tokens": usage.get("cached_tokens")})
    with _shared_gate(ledger):
        if ledger._closed:
            raise ValueError("reconciliation requires an open ledger")
        row = ledger.connection.execute("SELECT ledger_json FROM run_budgets WHERE run_id=?", (run_id,)).fetchone()
        actions = json.loads(row[0])["actions"] if row else []
        if sum(a["kind"] == "http" and a["id"] == attempt_id for a in actions) != 1:
            raise ValueError("original HTTP attempt missing")
        return ledger.settle(run_id, attempt_id, event)


def _sqlite_busy(exc):
    code = getattr(exc, "sqlite_errorcode", None)
    return (isinstance(code, int) and code & 0xff in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}) or any(
        text in str(exc).lower() for text in ("database is locked", "database table is locked"))


def settle_late_with_retry(budget, event):
    """Bound transient SQLite retries; never redispatch the provider request."""
    for index in range(3):
        admitted = budget.ledger.lock.acquire(timeout=.25)
        token = _settlement_timeout.set(.25)
        try:
            if admitted:
                try:
                    if budget.ledger._closed and not budget.ledger.database_path:
                        break
                    budget.after_attempt(event)
                    _settle_population_action(budget.ledger, budget.run_id,
                                              event.get("attempt_id"))
                    return
                except sqlite3.OperationalError as exc:
                    if not _sqlite_busy(exc):
                        break
                except Exception:
                    break
        finally:
            _settlement_timeout.reset(token)
            if admitted:
                budget.ledger.lock.release()
        if index < 2:
            time.sleep(.1)
    _save_unresolved(budget.ledger, budget.run_id, event)


def settle_timeout_nonblocking(budget, event):
    """Do not wait for either shared gate or SQLite's busy handler at timeout."""
    ledger = budget.ledger
    with _shared_gate(ledger, blocking=False) as admitted:
        if admitted and not ledger._closed:
            busy_timeout = ledger.connection.execute("PRAGMA busy_timeout").fetchone()[0]
            try:
                ledger.connection.execute("PRAGMA busy_timeout = 0")
                budget.after_attempt(event)
                return
            except sqlite3.OperationalError as exc:
                if not _sqlite_busy(exc):
                    raise
            finally:
                ledger.connection.execute(f"PRAGMA busy_timeout = {busy_timeout}")
    threading.Thread(target=settle_late_with_retry, args=(budget, dict(event)),
                     name="showcase-timeout-settlement", daemon=True).start()


def settle_closed(original, run_id, attempt_id, event):
    from .run_budget import RunBudgetLedger
    usage = provider_usage(event)
    if not original.database_path:
        return  # An in-memory ledger has no surviving storage.
    ledger = RunBudgetLedger(database_path=original.database_path)
    try:
        # Only an existing original HTTP reservation may be settled. No ensure/reserve.
        with _shared_gate(ledger):
            row = ledger.connection.execute("SELECT ledger_json FROM run_budgets WHERE run_id=?", (run_id,)).fetchone()
        actions = json.loads(row[0])["actions"] if row else []
        matches = [a for a in actions if a["id"] == attempt_id and a["kind"] == "http"]
        if len(matches) != 1 or matches[0]["status"] not in {"reserved", "error", "unknown", "success"}:
            return
        if not ledger.settle(run_id, attempt_id, event):
            return
        _settle_population_action(ledger, run_id, attempt_id)
        evidence = dict(run_id=run_id, attempt_id=attempt_id, observed_at=time.time(), usage=usage)
        if original.late_usage_evidence_dir is not None:
            directory = Path(original.late_usage_evidence_dir)
            directory.mkdir(parents=True, exist_ok=True)
            with (directory / (uuid4().hex + ".json")).open("x", encoding="utf-8") as stream:
                json.dump(evidence, stream, sort_keys=True)
    finally:
        ledger.close()


def _settle_population_action(ledger, run_id, attempt_id):
    """Settle only the physical resource state; mathematical outcome stays frozen."""
    if not ledger.database_path or not isinstance(attempt_id, str):
        return
    row = ledger.connection.execute(
        "SELECT ledger_json FROM run_budgets WHERE run_id=?", (run_id,)
    ).fetchone()
    if row is None:
        return
    actions = json.loads(row[0])["actions"]
    http = next((item for item in actions if item.get("id") == attempt_id
                 and item.get("kind") == "http"), None)
    population_action_id = http.get("population_action_id") if http else None
    if not isinstance(population_action_id, str):
        return
    connection = sqlite3.connect(ledger.database_path, timeout=1, check_same_thread=False)
    try:
        connection.row_factory = sqlite3.Row
        from types import SimpleNamespace

        from .solver_harness.population_store import command
        from .solver_harness.storage import SolverStateStore

        harness = SimpleNamespace(
            _state_store=SolverStateStore(connection),
            _population_owner=None,
            _event_observer=None,
        )
        command(harness, run_id, "physical_settlement", action_id=population_action_id)
    except sqlite3.OperationalError as exc:
        if not _sqlite_busy(exc):
            raise
    finally:
        connection.close()
