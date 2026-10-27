"""Keep #97 runtime ledgers available until late usage can be settled."""

import json
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path

_UNRESOLVED_STATUSES = {"reserved", "pending", "error", "unknown"}


def cleanup_runtime_storage(storage, run_ids, *, grace_seconds, preserve=False,
                            retention_reason=None):
    """Release settled Jobs; retain uncertain dispatches or attempts for reconciliation."""
    runtime_path = Path(storage.name)
    database_path = runtime_path / "nonstream" / "showcase.sqlite3"
    # TemporaryDirectory's finalizer must not erase a pending ledger on GC/exit.
    storage._finalizer.detach()
    if preserve and not run_ids:
        reason = "dispatch_identity_unresolved"
    elif preserve:
        reason = retention_reason or "job_archive_incomplete"
    else:
        reason = "pending_settlement"
    _record_retention(runtime_path, run_ids, reason)
    if preserve:
        return "retained"
    deadline = time.monotonic() + max(1.0, float(grace_seconds))
    if not _has_unresolved_attempts(database_path, run_ids):
        try:
            storage.cleanup()
            return "complete"
        except OSError:
            pass

    _start_deferred_cleanup(storage, database_path, run_ids, deadline)
    return "deferred"


def _start_deferred_cleanup(storage, database_path, run_ids, deadline):
    """Retry release after worker connections and late callbacks have closed."""
    def wait_and_cleanup():
        """Wait for late settlement, then release the temporary directory."""
        while True:
            try:
                if not _has_unresolved_attempts(database_path, run_ids):
                    storage.cleanup()
                    return
            except OSError:
                pass
            if time.monotonic() >= deadline:
                _record_retention(Path(storage.name), run_ids, "settlement_grace_expired")
                return
            time.sleep(0.05)

    threading.Thread(
        target=wait_and_cleanup,
        name="star-readiness-97-runtime-cleanup",
        daemon=False,
    ).start()
    return "deferred"


def _record_retention(path, run_ids, reason):
    """Leave a prompt-free receipt beside the private database for manual review."""
    (path / "retention.json").write_text(
        json.dumps({"reason": reason, "run_ids": list(run_ids)}, sort_keys=True), encoding="utf-8"
    )


def _has_unresolved_attempts(database_path, run_ids):
    """Read persisted Job and HTTP states to guard workers and late callbacks."""
    if not run_ids or not database_path.is_file():
        return False
    try:
        with closing(sqlite3.connect(database_path.as_uri() + "?mode=ro", uri=True,
                                    timeout=0.2)) as connection:
            active = connection.execute(
                "SELECT 1 FROM workspace_jobs WHERE job_id IN ({}) "
                "AND status IN ('queued','running','waiting_input')".format(
                    ",".join("?" for _ in run_ids)
                ), tuple(run_ids),
            ).fetchone()
            if active:
                return True
            rows = connection.execute(
                "SELECT ledger_json FROM run_budgets WHERE run_id IN ({})".format(
                    ",".join("?" for _ in run_ids)
                ),
                tuple(run_ids),
            ).fetchall()
    except (OSError, sqlite3.Error):
        return True
    if len(rows) != len(set(run_ids)):
        return True
    for (serialized,) in rows:
        try:
            actions = json.loads(serialized)["actions"]
        except (KeyError, TypeError, ValueError):
            return True
        if any(
            action.get("kind") == "http"
            and action.get("status") in _UNRESOLVED_STATUSES
            for action in actions
            if isinstance(action, dict)
        ):
            return True
    return False
