"""Cooperative action fences shared by model, tools and LangGraph execution."""

import time
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps

from .star_product_modes import BEST_EFFORT_MODES

_current = ContextVar("showcase_run_control", default=None)


class RunStopped(RuntimeError):
    def __init__(self, category):
        super().__init__(category)
        self.category = category


class RunControl:
    def __init__(self, store, run_id, budget, checkpointer=None):
        self.store, self.run_id, self.budget = store, run_id, budget
        self.checkpointer = checkpointer

    def check(self, *, allow_expired_selection=False):
        row = self.store.control_status(self.run_id)
        if row is None or row["status"] not in {"running", "queued"}:
            raise RunStopped(
                "run_canceled" if row and row["status"] == "canceled" else "run_stopped"
            )
        if time.time() >= self.budget.snapshot()["deadline_at"]:
            if self.store.job_identity(self.run_id).get("solver_mode") in BEST_EFFORT_MODES:
                if allow_expired_selection:
                    return
                raise RunStopped("run_deadline_exhausted")
            self.store.fail_job(self.run_id, "run_deadline_exhausted", execution_mode="live")
            if self.checkpointer is not None:
                self.checkpointer.stop(self.run_id, "FAILED", "run_deadline_exhausted")
            raise RunStopped("run_deadline_exhausted")


def check_control(*, allow_expired_selection=False):
    control = _current.get()
    if control is not None:
        control.check(allow_expired_selection=allow_expired_selection)
    else:
        from .run_budget import current_budget

        budget = current_budget()
        if budget is not None and time.time() >= budget.snapshot()["deadline_at"]:
            raise RunStopped("run_deadline_exhausted")


@contextmanager
def bind_control(control):
    token = _current.set(control)
    try:
        yield control
    finally:
        _current.reset(token)


def controlled_action(function):
    @wraps(function)
    def call(*args, **kwargs):
        check_control()
        result = function(*args, **kwargs)
        try:
            check_control()
        except RunStopped:
            control = _current.get()
            if control is not None and hasattr(result, "result_summary"):
                control.store.append_event(
                    control.run_id,
                    {
                        "type": "tool_call_result",
                        "name": args[1],
                        "status": result.status,
                        "tool_call_id": result.tool_call_id,
                        "result_summary": result.result_summary,
                        "error_category": result.error_category,
                        "late_result": True,
                    },
                )
            raise
        return result

    return call


def assert_dispatch_allowed(connection, run_id):
    """The committed budget reservation linearizes dispatch against cancel.

    A reserved HTTP/tool action is already in flight for control purposes;
    no network or tool handler runs while holding the SQLite transaction.
    """
    if connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='workspace_jobs'"
    ).fetchone():
        row = connection.execute(
            "SELECT status FROM workspace_jobs WHERE job_id=?", (run_id,)
        ).fetchone()
        if row is not None and row[0] != "running":
            raise RunStopped("run_stopped")
