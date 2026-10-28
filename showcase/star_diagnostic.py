"""Explicit in-process fake batches. There is deliberately no live dispatch port."""
import json
import os
import socket
import sqlite3
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from .run_budget import RunBudgetLedger, RunBudgetLimits, freeze_budget
from .star_diagnostic_registration import (
    _request,
    digest,
    validate,
    write_new,
)
from .star_diagnostic_store import claim, default_registry, initialize, mark, status


@contextmanager
def socket_free():
    # A fake-only command owns its process; neither localhost nor DNS is allowed.
    with ExitStack() as stack:
        for name in ("socket", "create_connection", "getaddrinfo", "socketpair"):
            stack.enter_context(patch.object(socket, name, side_effect=RuntimeError("diagnostic_socket_forbidden")))
        yield


def process_identity():
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        handle = kernel32.GetCurrentProcess()
        if not kernel32.GetProcessTimes(handle, ctypes.byref(created),
                ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user)):
            raise OSError("diagnostic_process_identity_unavailable")
        creation = ((created.dwHighDateTime << 32) + created.dwLowDateTime) / 1e7 - 11644473600
    else:
        import subprocess
        creation = subprocess.check_output(["ps", "-p", str(os.getpid()), "-o", "lstart="], text=True).strip()
    return dict(pid=os.getpid(), process_created_at=creation)


class DiagnosticJob:
    def __init__(self, registration, archive, registry=None):
        self.registration, self.archive = Path(registration).resolve(), Path(archive).resolve()
        self.registry = Path(registry) if registry is not None else default_registry()
        self.manifest = json.loads((self.registration / "manifest.json").read_text(encoding="utf-8"))

    def snapshot(self):
        from .star_diagnostic_monitor import monitor
        return monitor(self.archive)

    def cancel(self):
        write_new(self.archive / "cancel.json", {"cancel": True})

    def continue_remaining(self, *, outcomes=None):
        return self.run(outcomes=outcomes, continuation=True)

    def run(self, *, outcomes=None, limit=None, cancel_after=None, continuation=False):
        with socket_free():
            return self._run(outcomes=outcomes, limit=limit, cancel_after=cancel_after,
                             continuation=continuation)

    def _run(self, *, outcomes, limit, cancel_after, continuation):
        validate(self.manifest, check_source=True)
        inputs = json.loads((self.registration / "private" / "inputs.json").read_text(encoding="utf-8"))
        requests = self.manifest["requests"]
        if len(inputs) != len(requests):
            raise ValueError("diagnostic_inputs_changed")
        for raw, frozen in zip(inputs, requests, strict=True):
            if (_request(raw, self.manifest["phase"]) != frozen["input_estimate"]
                    or any(digest(raw[k]) != frozen[k + "_sha256"] for k in ("question", "prompt", "schema"))
                    or any(raw[k] != frozen[k] for k in ("arm", "question_id", "timeout_seconds"))):
                raise ValueError("diagnostic_inputs_changed")
        allowed = {"success", "unknown", "missing_usage", "protocol_failed", "crash", "intent_crash", "archive_failure", "disconnect"}
        outcomes = outcomes or ["success"] * len(requests)
        if any(o not in allowed for o in outcomes) or len(outcomes) != len(requests):
            raise ValueError("diagnostic_fake_script_invalid")
        if limit is not None and (self.manifest["phase"] != "P" or limit != 3):
            raise ValueError("diagnostic_control_boundary_invalid")
        if not self.manifest["conditions_met"]:
            return dict(status="not_started", dispatched=0)
        if not self.manifest["window"]["start"] <= time.time() < self.manifest["window"]["end"]:
            raise ValueError("diagnostic_outside_window")
        claim(self.registry, self.manifest, self.archive, continuation=continuation)
        db = None
        ledger = None
        terminal = "interrupted"
        try:
            if not continuation:
                self.archive.mkdir(parents=True, exist_ok=False)
                (self.archive / "private").mkdir()
                write_new(self.archive / "manifest.json", self.manifest)
                write_new(self.archive / "process.json", dict(**process_identity(),
                          stdout=str(self.archive / "stdout.log"), stderr=str(self.archive / "stderr.log"),
                          monitor_argv=["uv", "run", "--offline", "python", "scripts/run_star_diagnostic_102.py",
                                        "monitor", "--archive", str(self.archive)]))
                for name in ("stdout.log", "stderr.log"):
                    (self.archive / name).touch(exist_ok=False)
            db = sqlite3.connect(self.archive / "batch.sqlite3")
            if not continuation:
                initialize(db, self.manifest)
            ledger = RunBudgetLedger(connection=db)
            done = db.execute("SELECT count(*) FROM diagnostic_dispatch").fetchone()[0]
            terminal = "completed"
            for position in range(done, len(requests)):
                if (self.archive / "cancel.json").exists() or (cancel_after is not None and position >= cancel_after):
                    terminal = "cancelled"
                    break
                if limit is not None and position >= limit:
                    terminal = "control_complete"
                    break
                request = requests[position]
                if time.time() >= self.manifest["window"]["end"]:
                    terminal = "deadline"
                    break
                run_id, attempt_id = request["run_id"], uuid4().hex
                deadline = min(time.time() + request["timeout_seconds"], self.manifest["window"]["end"])
                db.execute("INSERT INTO diagnostic_dispatch VALUES (?,?,?,?,?,NULL)",
                           (position, run_id, attempt_id, deadline, "intent"))
                db.commit()
                outcome = outcomes[position]
                if outcome == "intent_crash":
                    raise InterruptedError("diagnostic_simulated_exit")
                workspace = self.archive / "private" / request["workspace_id"]
                workspace.mkdir(exist_ok=False)
                write_new(workspace / "input.json", inputs[position])
                budget = ledger.ensure(run_id, RunBudgetLimits(max_model_calls=1, max_http_attempts=1,
                            max_tool_calls=0, max_tokens=65536, max_runtime_seconds=request["timeout_seconds"]),
                            deadline_at=deadline)
                call = budget.model_call("diagnostic", deadline_at=deadline)
                event = dict(attempt_id=attempt_id, logical_call_id=call.logical_call_id,
                             max_tokens=16384, deadline_at=deadline, status="unknown")
                call.before_attempt(event, request["input_estimate"])
                if outcome == "crash":
                    raise InterruptedError("diagnostic_simulated_exit")
                unknown = outcome in {"unknown", "disconnect", "missing_usage"}
                if not unknown:
                    event.update(status="success", prompt_tokens=7, completion_tokens=3, total_tokens=10)
                call.after_attempt(event)
                state = "unknown" if unknown else "protocol_failed" if outcome == "protocol_failed" else "completed"
                result_hash = None
                if not unknown:
                    # Fixed fake visible content only; never persist hidden thinking.
                    visible = {"visible_response": "fake complete reply", "answer": "fake answer"}
                    result_hash = digest(visible)
                    if outcome == "archive_failure":
                        raise OSError("diagnostic_simulated_archive_failure")
                    write_new(workspace / "visible.json", visible)
                db.execute("UPDATE diagnostic_dispatch SET status=?,result_sha256=? WHERE position=?",
                           (state, result_hash, position))
                freeze_budget(db, run_id)
                db.commit()
                with (self.archive / "stdout.log").open("a", encoding="utf-8") as log:
                    log.write(json.dumps(dict(event=state, position=position, run_id=run_id)) + "\n")
                if unknown:
                    terminal = "unknown"
                    break
        except InterruptedError:
            terminal = "interrupted"
        except OSError:
            terminal = "archive_failed"
        finally:
            if db is not None:
                try:
                    status(db, terminal)
                finally:
                    db.close()
            mark(self.registry, self.manifest, terminal)
        return self.snapshot()

    def reconcile(self, run_id, attempt_id, *, prompt_tokens, completion_tokens, total_tokens):
        """Trusted offline late usage only; no result recovery or batch resume."""
        with socket_free():
            db = sqlite3.connect(self.archive / "batch.sqlite3")
            try:
                row = db.execute("SELECT 1 FROM diagnostic_dispatch WHERE run_id=? AND attempt_id=?",
                                 (run_id, attempt_id)).fetchone()
                if row is None:
                    raise ValueError("diagnostic_original_attempt_missing")
                ledger = RunBudgetLedger(connection=db)
                if ledger.snapshot(run_id) is None or not ledger.attempts(run_id):
                    raise ValueError("diagnostic_original_reservation_missing")
                values = (prompt_tokens, completion_tokens, total_tokens)
                if any(type(v) is not int or v < 0 for v in values) or total_tokens != prompt_tokens + completion_tokens:
                    raise ValueError("diagnostic_usage_invalid")
                return ledger.settle(run_id, attempt_id, dict(status="success", prompt_tokens=prompt_tokens,
                                     completion_tokens=completion_tokens, total_tokens=total_tokens))
            finally:
                db.close()
