"""UTC deadline clock that fails closed when the system clock rolls back."""

import threading


def guarded_utc_clock(wall_clock):
    """Preserve UTC observations exactly; latch expiration on any rollback."""
    lock = threading.Lock()
    previous = float("-inf")

    def clock():
        nonlocal previous
        with lock:
            now = wall_clock()
            previous = now if now >= previous else float("inf")
            return previous

    return clock
