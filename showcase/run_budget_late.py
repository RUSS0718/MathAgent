"""Late usage settlement reopens only the original S3 database, never dispatch."""
import json
import logging
import sqlite3
import time
from pathlib import Path
from uuid import uuid4

from llm_response import provider_usage


def settle_late_with_retry(budget, event):
    """Bound transient SQLite retries; never redispatch the provider request."""
    logger = logging.getLogger(__name__)
    for index in range(3):
        try:
            budget.after_attempt(event)
            return
        except sqlite3.OperationalError as exc:
            code = getattr(exc, "sqlite_errorcode", None)
            locked = (isinstance(code, int) and code & 0xff in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}) or any(
                text in str(exc).lower() for text in ("database is locked", "database table is locked"))
            if not locked:
                break
            if index < 2:
                time.sleep(.1)
        except Exception:
            break
    # The persisted attempt and its reservation remain unresolved. Do not log
    # provider bodies or usage; the original run/attempt IDs support review.
    logger.warning("late settlement unresolved: run_id=%s attempt_id=%s",
                   budget.run_id, event.get("attempt_id"))

def settle_closed(original, run_id, attempt_id, event):
    from .run_budget import RunBudgetLedger
    usage = provider_usage(event)
    if not original.database_path:
        return  # An in-memory ledger has no surviving storage.
    ledger = RunBudgetLedger(database_path=original.database_path)
    try:
        # Only an existing original HTTP reservation may be settled. No ensure/reserve.
        with ledger.lock:
            row = ledger.connection.execute("SELECT ledger_json FROM run_budgets WHERE run_id=?", (run_id,)).fetchone()
        actions = json.loads(row[0])["actions"] if row else []
        matches = [a for a in actions if a["id"] == attempt_id and a["kind"] == "http"]
        if len(matches) != 1 or matches[0]["status"] not in {"reserved", "error", "unknown", "success"}:
            return
        if not ledger.settle(run_id, attempt_id, event):
            return
        evidence = dict(run_id=run_id, attempt_id=attempt_id, observed_at=time.time(), usage=usage)
        if original.late_usage_evidence_dir is not None:
            directory = Path(original.late_usage_evidence_dir)
            directory.mkdir(parents=True, exist_ok=True)
            with (directory / (uuid4().hex + ".json")).open("x", encoding="utf-8") as stream:
                json.dump(evidence, stream, sort_keys=True)
    finally:
        ledger.close()
