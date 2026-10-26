"""Late usage settlement reopens only the original S3 database, never dispatch."""
import json
import time
from pathlib import Path
from uuid import uuid4

from llm_response import provider_usage


def settle_closed(original, run_id, attempt_id, event):
    from .run_budget import RunBudgetLedger
    usage = provider_usage(event)
    if not original.database_path or all(value is None for value in usage.values()):
        return  # An in-memory ledger has no surviving storage; no fabricated usage.
    ledger = RunBudgetLedger(database_path=original.database_path)
    try:
        # Only an existing original HTTP reservation may be settled. No ensure/reserve.
        with ledger.lock:
            row = ledger.connection.execute("SELECT ledger_json FROM run_budgets WHERE run_id=?", (run_id,)).fetchone()
        actions = json.loads(row[0])["actions"] if row else []
        matches = [a for a in actions if a["id"] == attempt_id and a["kind"] == "http"]
        if len(matches) != 1 or matches[0]["status"] not in {"reserved", "error", "unknown"}:
            return
        ledger.settle(run_id, attempt_id, event)
        evidence = dict(run_id=run_id, attempt_id=attempt_id, observed_at=time.time(), usage=usage)
        if original.late_usage_evidence_dir is not None:
            directory = Path(original.late_usage_evidence_dir)
            directory.mkdir(parents=True, exist_ok=True)
            with (directory / (uuid4().hex + ".json")).open("x", encoding="utf-8") as stream:
                json.dump(evidence, stream, sort_keys=True)
    finally:
        ledger.close()
