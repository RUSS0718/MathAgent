"""Bind provider work to an admitted population action's reserved ledger slots."""

from contextlib import contextmanager
from contextvars import ContextVar

_action = ContextVar("showcase_population_action", default=None)


@contextmanager
def bind_population_action(action_id, owner):
    token = _action.set((action_id, owner))
    try:
        yield
    finally:
        _action.reset(token)


def current_population_action():
    return _action.get()


def resize_input_hold(reserved, input_estimate, summary, limits, floor, remaining_seconds):
    """Grow one input hold inside its ledger transaction, preserving every other hold."""
    from ..run_budget import BudgetExhausted

    delta = input_estimate - reserved["input_estimate"]
    if summary["charged_tokens"] + delta + floor.get("tokens", 0) > limits["max_tokens"]:
        raise BudgetExhausted("population_input_reservation_exhausted")
    if remaining_seconds < floor.get("time_seconds", 0):
        raise BudgetExhausted("population_closing_time_reserve_unavailable")
    reserved.setdefault("admitted_input_estimate", reserved["input_estimate"])
    reserved["input_estimate"] = input_estimate
