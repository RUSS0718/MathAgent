"""Keep sanitized attempt projections aligned with late response settlement."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from llm_response import public_attempt


class MeteredAttemptEvent(dict[str, Any]):
    """Dictionary event with in-memory listeners for late settlement only."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.public_projections: list[dict[str, Any]] = []
        self.late_callback_received = False


def bind_attempt_projection(event: dict[str, Any], projection: dict[str, Any]) -> None:
    """Attach the adapter's public view to the mutable metered attempt event."""
    lock = getattr(event, "state_lock", None)
    if lock is None:
        return
    with lock:
        if event.late_callback_received:
            _refresh_attempt_projection(event, (projection,))
        else:
            event.public_projections.append(projection)


def refresh_attempt_projection(event: Mapping[str, Any]) -> None:
    """Refresh an attached public view after the provider attempt changes."""
    lock = getattr(event, "state_lock", None)
    if lock is None:
        return
    with lock:
        _refresh_attempt_projection(event)


def _refresh_attempt_projection(event: Mapping[str, Any], projections=None) -> None:
    """Refresh projections while the owning attempt lock is held."""
    attached = getattr(event, "public_projections", ())
    projections = attached if projections is None else projections
    for projection in projections:
        projection.update(
            public_attempt(
                event,
                run_id=projection.get("run_id"),
                role=projection.get("role"),
            )
        )
    if projections is attached and isinstance(attached, list):
        attached.clear()
