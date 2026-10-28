"""Read committed diagnostic/S3 state without constructing a writer or runner."""
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from .run_budget import _summary
from .star_diagnostic_registration import identifier, validate

STATUSES = {"running", "completed", "control_complete", "cancelled", "deadline", "unknown",
            "interrupted", "archive_failed"}


def monitor(archive):
    archive = Path(archive).resolve()
    unavailable = dict(status="unavailable", charged_tokens=None, reserved_tokens=None,
                       remaining_tokens=None, remote_concurrency="unknown", cost=None)
    database = archive / "batch.sqlite3"
    if not database.is_file():
        return unavailable
    try:
        # A read-only open must not create WAL shared memory during recovery.
        wal = Path(str(database) + "-wal")
        if wal.exists() and wal.stat().st_size and not Path(str(database) + "-shm").exists():
            return unavailable
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=.2)) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            raw, state, last = db.execute("SELECT manifest,status,last_event FROM diagnostic_batch").fetchone()
            manifest = validate(json.loads(raw))
            rows = db.execute("SELECT position,run_id,attempt_id,deadline,status,result_sha256 FROM diagnostic_dispatch ORDER BY position").fetchall()
            budgets = dict(db.execute("SELECT run_id,ledger_json FROM run_budgets").fetchall())
            if state not in STATUSES or last not in STATUSES | {"started"}:
                raise ValueError("diagnostic_snapshot_invalid")
            charged = reserved = completed = unknown = 0
            totals = dict(prompt_tokens=0, completion_tokens=0, total_tokens=0)
            results = []
            unconfirmed = 0
            for position, run_id, attempt, deadline, dispatch, result_hash in rows:
                if (manifest["requests"][position]["run_id"] != run_id
                        or dispatch not in {"intent", "unknown", "completed", "protocol_failed"}):
                    raise ValueError("diagnostic_snapshot_invalid")
                identifier(run_id)
                identifier(attempt)
                original = json.loads(budgets[run_id]) if run_id in budgets else None
                summary = _summary(original) if original is not None else None
                if summary is None or summary["http_attempts"] != 1:
                    unconfirmed += 65536
                    unknown += 1
                    summary = None
                else:
                    charged += summary["charged_tokens"]
                    reserved += summary["reserved_tokens"]
                    unknown += bool(summary["unresolved_attempts"] or summary["unknown_attempts"])
                    for key in totals:
                        value = summary["provider_known"][key]
                        if value is None or totals[key] is None:
                            totals[key] = None
                        else:
                            totals[key] += value
                completed += dispatch in {"completed", "protocol_failed"}
                results.append(dict(position=position, run_id=run_id, attempt_id=attempt,
                                    deadline_at=deadline, status=dispatch,
                                    result_sha256=result_hash if isinstance(result_hash, str)
                                    and len(result_hash) == 64 and all(c in "0123456789abcdef" for c in result_hash) else None,
                                    budget=summary))
            if unconfirmed:
                totals = {key: None for key in totals}
            return dict(status=state, mode="fake", registration_id=manifest["registration_id"],
                        manifest_sha256=manifest["sha256"], planned=len(manifest["requests"]),
                        dispatched=len(rows), completed=completed, unknown=unknown,
                        not_dispatched=len(manifest["requests"]) - len(rows),
                        charged_tokens=charged if not unconfirmed else None,
                        reserved_tokens=reserved if not unconfirmed else None,
                        unconfirmed_reserved_tokens=unconfirmed,
                        conservative_charged_tokens=charged + unconfirmed,
                        remaining_tokens=max(0, manifest["budget"]["tokens"] - charged - unconfirmed),
                        remaining_requests=manifest["budget"]["requests"] - len(rows),
                        provider_known=totals, cost=None, remote_concurrency="unknown",
                        last_event=last, results=results)
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError, IndexError):
        return unavailable
