"""Bound one research operation; late thread results never enter Run state."""

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from contextvars import copy_context


def bounded_research(operation, request):
    timeout = request["timeout_seconds"]
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(copy_context().run, operation, request)
    try:
        return future.result(timeout=timeout)
    except FutureTimeout as exc:
        error = TimeoutError("research_deadline_exceeded; execution_outcome_unknown")
        error.research_status = "unknown_outcome"
        raise error from exc
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
