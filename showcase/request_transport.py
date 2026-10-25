"""Bounded response reader for metered product model requests."""

from __future__ import annotations

import json
import queue
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any

import requests


def response_events(
    url: str,
    *,
    deadline: float,
    timeout: float,
    on_late_response: Callable[[requests.Response, bytes, float | None, float], None] | None = None,
    **request_kwargs: Any,
) -> Iterator[tuple[str, Any]]:
    """Yield response headers, body bytes and completion under an absolute deadline.

    Requests performs blocking I/O, so a daemon reader thread feeds a bounded
    queue while the caller enforces the wall-clock deadline. When the caller
    reaches its deadline, it detaches while the reader may finish later to settle
    response metadata. That local timeout never implies provider cancellation.
    """
    events: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=16)
    canceled = threading.Event()
    detached = threading.Event()
    deadline_hit = False
    started = time.monotonic()

    def publish(event: tuple[str, Any]) -> bool:
        while not canceled.is_set() and not detached.is_set():
            try:
                events.put(event, timeout=0.05)
                return True
            except queue.Full:
                continue
        return False

    def read_response() -> None:
        response = None
        response_body = bytearray()
        try:
            response = requests.post(url, timeout=timeout, stream=True, **request_kwargs)
            response_headers_at = time.monotonic()
            publish(("headers", response))
            if callable(getattr(response, "iter_content", None)):
                body_chunks = response.iter_content(chunk_size=1)
            else:
                body_chunks = (bytes((byte,)) for byte in json.dumps(response.json()).encode())
            for chunk in body_chunks:
                if canceled.is_set():
                    return
                if detached.is_set() and time.monotonic() >= deadline + timeout:
                    return
                if chunk:
                    if len(response_body) < 8 * 1024 * 1024:
                        response_body.extend(chunk)
                    publish(("bytes", chunk))
            if detached.is_set() and on_late_response is not None and len(response_body) < 8 * 1024 * 1024:
                on_late_response(
                    response,
                    bytes(response_body),
                    response_headers_at - started if response_headers_at is not None else None,
                    time.monotonic() - started,
                )
            else:
                publish(("complete", None))
        except Exception as exc:  # forwarded to the synchronous caller
            publish(("error", exc))
        finally:
            if response is not None and callable(getattr(response, "close", None)):
                try:
                    response.close()
                except Exception:
                    pass

    worker = threading.Thread(
        target=read_response,
        name=f"showcase-http-reader-{threading.current_thread().name}",
        daemon=True,
    )
    worker.start()
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                deadline_hit = True
                detached.set()
                raise requests.ReadTimeout("logical_deadline_exceeded")
            try:
                kind, value = events.get(timeout=min(remaining, 0.05))
            except queue.Empty:
                continue
            if kind == "error":
                raise value
            yield kind, value
            if kind in {"complete", "error"}:
                return
    finally:
        if not deadline_hit:
            canceled.set()
