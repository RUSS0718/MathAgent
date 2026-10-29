"""Deadline-aware handoff for local processing of metered responses."""

import threading
import time
from contextvars import Context

import requests


def process_before_deadline(process, deadline, on_late):
    """Run processing without waiting for a timed-out worker or its callback.

    Exactly one side owns the result: the caller before the deadline, or the
    late callback afterwards. The daemon thread is not cancelled by timeout.
    """
    lock = threading.Lock()
    ready = threading.Event()
    state = {"detached": False, "complete": False, "result": None, "error": None}

    def run():
        try:
            result, error = Context().run(process), None
        except BaseException as exc:  # relay the same exception to the caller
            result, error = None, exc
        with lock:
            state.update(complete=True, result=result, error=error)
            detached = state["detached"]
            ready.set()
        if detached:
            on_late(result, error)

    threading.Thread(target=run, name="showcase-response-processing", daemon=True).start()
    while not ready.is_set():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        ready.wait(remaining)
    if not lock.acquire(timeout=max(0, deadline - time.monotonic())):
        def detach_later():
            with lock:
                state["detached"] = True
                completed = state["complete"]
                result, error = state["result"], state["error"]
            if completed:
                on_late(result, error)

        threading.Thread(target=detach_later, name="showcase-late-handoff", daemon=True).start()
        raise requests.ReadTimeout("logical_deadline_exceeded_during_processing")
    try:
        if state["complete"] and time.monotonic() < deadline:
            result, error = state["result"], state["error"]
            if error is not None:
                raise error
            return result
        state["detached"] = True
        completed = state["complete"]
        result, error = state["result"], state["error"]
    finally:
        lock.release()
    if completed:
        threading.Thread(target=on_late, args=(result, error),
                         name="showcase-late-processing", daemon=True).start()
    raise requests.ReadTimeout("logical_deadline_exceeded_during_processing")
