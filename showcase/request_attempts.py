"""Run-local collection of sanitized provider attempts, including failures."""

from __future__ import annotations

from contextvars import ContextVar
from functools import wraps
from typing import Any

from llm_response import public_attempt

from .run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget, current_budget

_capture: ContextVar[Any] = ContextVar("showcase_attempt_capture", default=None)


def record_attempts(events, metadata=None):
    capture = _capture.get()
    records = []
    for event in events:
        record = public_attempt(
            event,
            run_id=capture[0] if capture else (metadata or {}).get("run_id"),
            role=(metadata or {}).get("role"),
        )
        records.append(record)
        if capture:
            capture[1].append(record)
            if capture[2]:
                capture[2]({"type": "request_attempt", "job_id": capture[0], "attempt": record})
    return tuple(records)


def capture_pipeline_attempts(function):
    @wraps(function)
    def run(self, run_id, *args, **kwargs):
        records = []
        token = _capture.set((run_id, records, kwargs.get("emit")))
        try:
            if current_budget() is None:
                if not hasattr(self, "_run_ledger"):
                    self._run_ledger = RunBudgetLedger()
                limits = RunBudgetLimits(**vars(getattr(self, "budget", RunBudgetLimits())))
                budget = self._run_ledger.ensure(run_id, limits)
            else:
                budget = current_budget()
            with bind_budget(budget):
                state = function(self, run_id, *args, **kwargs)
            state["budget"] = budget.snapshot()
            state["request_attempts"] = records
            return state
        finally:
            _capture.reset(token)

    return run
