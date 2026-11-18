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
