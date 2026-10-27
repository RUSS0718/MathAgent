"""Bounded response reader for metered product model requests."""

from __future__ import annotations

import inspect
import json
import queue
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any
from urllib.parse import urlsplit

import requests

_LateResponseCallback = (
    Callable[[requests.Response, bytes, float | None, float], None]
    | Callable[[requests.Response, bytes, float | None, float, bool], None]
)


def strict_loopback_post(url: str, **kwargs: Any) -> requests.Response:
    """Post only to IPv4 loopback without environment proxies or redirects."""
    target = urlsplit(url)
    if ("proxies" in kwargs or target.scheme != "http" or target.hostname != "127.0.0.1"
            or target.username is not None or target.password is not None):
        raise ValueError("strict_loopback_url_required")
    with requests.Session() as session:
        session.trust_env = False
        response = session.post(url, allow_redirects=False, **kwargs)
        if 300 <= response.status_code < 400:
            response.close()
            raise requests.HTTPError("strict_loopback_redirect_rejected")
        return response


def _invoke_late_response(
    callback: _LateResponseCallback,
    response: requests.Response,
    body: bytes,
    response_headers_seconds: float | None,
    total_seconds: float,
    body_complete: bool,
) -> None:
    """Call either the legacy four-argument or current five-argument callback."""
    arguments = (response, body, response_headers_seconds, total_seconds)
    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):
        callback(*arguments, body_complete)
        return
    try:
        signature.bind(*arguments, body_complete)
    except TypeError:
        if body_complete:
            callback(*arguments)
    else:
        callback(*arguments, body_complete)


def response_events(
    url: str,
    *,
    deadline: float,
    timeout: float,
    loopback_only: bool = False,
    on_late_response: _LateResponseCallback | None = None,
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
        response_headers_seconds = None
        response_body = bytearray()
        body_complete = False
        late_callback_invoked = False

        def settle_late(body_complete):
            nonlocal late_callback_invoked
            if (on_late_response is None or response is None or late_callback_invoked
                    or len(response_body) >= 8 * 1024 * 1024):
                return
            late_callback_invoked = True
            try:
                _invoke_late_response(
                    on_late_response,
                    response,
                    bytes(response_body),
                    response_headers_seconds,
                    time.monotonic() - started,
                    body_complete,
                )
            except Exception:
                pass

        try:
            post = strict_loopback_post if loopback_only else requests.post
            response = post(url, timeout=timeout, stream=True, **request_kwargs)
            response_headers_at = time.monotonic()
            response_headers_seconds = response_headers_at - started
            publish(("headers", response))
            if callable(getattr(response, "iter_content", None)):
                body_chunks = response.iter_content(chunk_size=1)
            else:
                body_chunks = (bytes((byte,)) for byte in json.dumps(response.json()).encode())
            for chunk in body_chunks:
                if canceled.is_set():
                    return
                if chunk:
                    if len(response_body) < 8 * 1024 * 1024:
                        response_body.extend(chunk)
                    if not detached.is_set():
                        publish(("bytes", chunk))
                if detached.is_set() and time.monotonic() >= deadline + timeout:
                    settle_late(False)
                    return
            body_complete = True
            if detached.is_set():
                settle_late(body_complete)
            else:
                publish(("complete", None))
        except Exception as exc:  # forwarded to the synchronous caller
            if detached.is_set():
                settle_late(body_complete)
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
