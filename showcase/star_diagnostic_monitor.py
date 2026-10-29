"""Read committed diagnostic/S3 state without constructing a writer or runner."""
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

from .run_budget import _summary
from .star_diagnostic_process import observe_process
from .star_diagnostic_registration import identifier, validate

STATUSES = {"running", "completed", "control_complete", "cancelled", "deadline", "unknown",
            "interrupted", "archive_failed"}


def _public_budget(state):
    # Reuse S3 arithmetic, then expose only numeric counters, never arbitrary ledger payloads.
    summary = _summary(state)
    result = {key: summary[key] for key in ("logical_calls", "http_attempts", "tool_calls",
              "charged_tokens", "reserved_tokens", "unknown_attempts", "unresolved_attempts", "deadline_at")}
    result["provider_known"] = summary["provider_known"]
    numbers = [v for k, v in result.items() if k != "provider_known"]
    numbers.extend(v for v in result["provider_known"].values() if v is not None)
    if any(type(v) not in {int, float} or not math.isfinite(v) or v < 0 for v in numbers):
        raise ValueError("diagnostic_metering_invalid")
    return result


def monitor(archive, *, _isolated=False):
    """Keep WAL mappings isolated from any in-process producer's writable SHM cache."""
    archive = Path(archive).resolve()
    unavailable = dict(status="unavailable", charged_tokens=None, reserved_tokens=None,
                       remaining_tokens=None, remote_concurrency="unknown", cost=None)
    database = archive / "batch.sqlite3"
    if not database.is_file():
        return unavailable
    try:
        if not _isolated:
            # Isolate even a DELETE header: a continuation may restore WAL before open.
            worker = subprocess.run(
                [sys.executable, "-B", "-m", "showcase.star_diagnostic_monitor", str(archive)],
                cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
                encoding="utf-8", timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            return json.loads(worker.stdout) if worker.returncode == 0 else unavailable
        # Closed legacy WAL archives need a writer-owned checkpoint, never recovery here.
        wal = Path(str(database) + "-wal")
        with database.open("rb") as stream:
            wal_mode = stream.read(20)[18:20] == b"\x02\x02"
        if wal_mode and (not wal.is_file() or not Path(str(database) + "-shm").is_file()):
            return unavailable
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro&readonly_shm=1", uri=True, timeout=.2)) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            raw, state, last, last_at = db.execute("SELECT manifest,status,last_event,last_event_at FROM diagnostic_batch").fetchone()
            manifest = validate(json.loads(raw))
            rows = db.execute("SELECT position,run_id,attempt_id,deadline,status,result_sha256 FROM diagnostic_dispatch ORDER BY position").fetchall()
            budgets = dict(db.execute("SELECT run_id,ledger_json FROM run_budgets").fetchall())
            if (state not in STATUSES or last not in STATUSES | {"started", "dispatch_intent", "reserved"}
                    or type(last_at) not in {int, float} or not math.isfinite(last_at)):
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
                summary = _public_budget(original) if original is not None else None
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
            try:
                process = json.loads((archive / "process.json").read_text(encoding="utf-8"))
                identity = {key: process[key] for key in ("pid", "process_created_at")}
                created = identity["process_created_at"]
                if not ((type(created) in {int, float} and math.isfinite(created) and created > 0)
                        or (isinstance(created, str) and re.fullmatch(r"[A-Za-z]{3} [A-Za-z]{3} [ 0-9]{2} [0-9:]{8} [0-9]{4}", created))):
                    raise ValueError("diagnostic_process_invalid")
                owner_state = observe_process(identity)
            except (OSError, ValueError, KeyError, TypeError):
                identity, owner_state = None, "unavailable"
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
                        last_event=last, last_event_at=last_at, results=results, process=identity,
                        process_state=owner_state,
                        restart_requires_review=state == "running" and owner_state in {"exited", "reused"},
                        stdout=str(archive / "stdout.log"), stderr=str(archive / "stderr.log"))
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError, IndexError,
            subprocess.TimeoutExpired):
        return unavailable


if __name__ == "__main__":
    print(json.dumps(monitor(sys.argv[1], _isolated=True), ensure_ascii=False, allow_nan=False))
