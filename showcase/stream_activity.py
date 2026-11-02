"""Small opt-in, redacted observer for provider stream activity."""

from collections.abc import Callable
from datetime import UTC, datetime


def notify(observer: Callable | None, kind: str, **fields) -> None:
    """Send timing/count evidence without ever forwarding stream text."""

    if not callable(observer):
        return
    payload = {"kind": kind, "at": datetime.now(UTC).isoformat()}
    payload.update({key: value for key, value in fields.items() if key != "text"})
    try:
        observer(payload)
    except Exception:
        return
