"""Keep #97 runtime ledgers available until late usage can be settled."""

import json
import sqlite3
import threading
import time
from pathlib import Path

_UNRESOLVED_STATUSES = {"reserved", "pending", "error", "unknown"}


def cleanup_runtime_storage(storage, run_ids, *, grace_seconds):
    """Clean an idle runtime immediately or defer cleanup while attempts remain unresolved."""
    runtime_path = Path(storage.name)
    database_path = runtime_path / "nonstream" / "showcase.sqlite3"
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
                try:
                    storage.cleanup()
                except OSError:
                    pass
                return
            time.sleep(0.05)

    threading.Thread(
        target=wait_and_cleanup,
        name="star-readiness-97-runtime-cleanup",
        daemon=True,
    ).start()
    return "deferred"


def _has_unresolved_attempts(database_path, run_ids):
    """Read only the persisted HTTP action states needed to guard late callbacks."""
    if not run_ids or not database_path.is_file():
        return False
    try:
        with sqlite3.connect(database_path, timeout=0.2) as connection:
            rows = connection.execute(
                "SELECT ledger_json FROM run_budgets WHERE run_id IN ({})".format(
                    ",".join("?" for _ in run_ids)
                ),
                tuple(run_ids),
            ).fetchall()
    except (OSError, sqlite3.Error):
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
