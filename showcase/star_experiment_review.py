"""Bound independent review waiting by the original round deadline/cancel."""

import queue
import threading


def await_review(reviewer, args, *, remaining, canceled):
    results = queue.SimpleQueue()

    def review():
        try:
            results.put((True, reviewer(*args)))
        except Exception as exc:
            results.put((False, type(exc).__name__))

    threading.Thread(target=review, daemon=True).start()
    while not canceled() and remaining() > 0:
        try:
            valid, result = results.get(timeout=max(0, min(.02, remaining())))
        except queue.Empty:
            continue
        if not valid:
            raise ValueError("independent_review_failed:" + result)
        return result
    return None  # A late review cannot overwrite an archived terminal decision.
