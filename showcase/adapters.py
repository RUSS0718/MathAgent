"""Product-level Intern and DeepAgents adapters.

The adapters normalize provider/framework behavior before it reaches Run state.
They are imported only by the explicit showcase profile and are safe to test
with an injected fake client.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import wraps
from typing import Any, Protocol

import requests

from .attempt_projection import bind_attempt_projection
from .graph import AgentDecision
from .request_attempts import record_attempts
from .run_budget import current_budget, request_timeout, scoped_deadline
from .run_control import controlled_action
from .run_service import AgentResult, RunRequest
from .tool_protocol import ToolProtocol, ToolRequest, parse_tool_requests


class AdapterError(RuntimeError):
    """Sanitized provider/framework failure used by the product surface."""

    def __init__(self, category: str, detail: str = "") -> None:
        super().__init__(category)
        self.category = category
        self.detail = detail


@dataclass(frozen=True)
class ModelResponse:
    """Provider-independent response returned by ``InternModelAdapter``."""

    text: str = ""
    tool_requests: tuple[ToolRequest, ...] = ()
    usage: Mapping[str, Any] = field(default_factory=dict)
    model_id: str = ""
    error_category: str | None = None
    request_attempts: tuple[Mapping[str, Any], ...] = ()
    returned_model: str | None = None
    finish_reason: str | None = None
    tool_protocol: ToolProtocol | None = None
    tool_request_error: str | None = None


class ContinuationTransport(Protocol):
    """Transport used to deliver one structured tool result back to Intern."""

    mode: str

    def continue_(
        self,
        messages: Sequence[Mapping[str, Any]],
        tool_request: ToolRequest,
        tool_result: Mapping[str, Any],
    ) -> ModelResponse:
        """Return the model continuation after a registered tool result."""


class ModelContinuationTransport:
    """Live continuation transport backed by the configured Intern client."""

    mode = "live"

    def __init__(self, model: InternModelAdapter) -> None:
        self.model = model

    def continue_(
        self,
        messages: Sequence[Mapping[str, Any]],
        tool_request: ToolRequest,
        tool_result: Mapping[str, Any],
    ) -> ModelResponse:
        if tool_request.protocol == "native":
            call = {
                "id": tool_request.tool_call_id,
                "type": "function",
                "function": {
                    "name": tool_request.name,
                    "arguments": json.dumps(
                        dict(tool_request.arguments), ensure_ascii=False, separators=(",", ":")
                    ),
                },
            }
            continuation = list(messages) + [
                {"role": "assistant", "content": None, "tool_calls": [call]},
                {
                    "role": "tool",
                    "tool_call_id": tool_request.tool_call_id,
                    "name": tool_request.name,
                    "content": json.dumps(dict(tool_result), ensure_ascii=False, default=str),
                },
            ]
        else:
            continuation = list(messages) + [
                {"role": "assistant", "content": tool_request.assistant_content},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"tool_result": dict(tool_result)}, ensure_ascii=False, default=str
                    ),
                },
            ]
        return self.model.complete(continuation, metadata={"role": "continuation"})


class InternModelAdapter:
    """Normalize the existing Intern client without changing its API."""

    def __init__(
        self,
        client: Any | None = None,
        *,
        model_id: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 16_384,
        client_timeout: int | None = None,
        client_retry: int | None = None,
        thinking_mode: bool | None = None,
        outbound_observer=None,
    ) -> None:
        self._client = client
        self.outbound_observer = outbound_observer
        self.model_id = model_id or os.environ.get("INTERN_MODEL", "intern-s2")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.client_timeout = client_timeout
        self.client_retry = client_retry
        self.thinking_mode = thinking_mode

    @controlled_action
    def complete(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        tools: Sequence[Mapping[str, Any]] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> ModelResponse:
        """Call the injected/current Intern client and parse safe tool markers."""

        client = self._get_client()
        normalized = [_normalize_message(message) for message in messages]
        kwargs: dict[str, Any] = {
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        # The repository client intentionally has no tools kwarg.  Injected
        # clients may opt in; old clients continue to receive the official text shape.
        if tools and _accepts_keyword(client.chat, "tools"):
            kwargs["tools"] = [dict(tool) for tool in tools]
        if self.thinking_mode is not None and _accepts_keyword(client.chat, "thinking_mode"):
            kwargs["thinking_mode"] = self.thinking_mode
        if _accepts_keyword(client.chat, "request_purpose"):
            kwargs["request_purpose"] = (metadata or {}).get("purpose") or (metadata or {}).get("role", "model_response")
        try:
            transport = getattr(client, "chat_response", client.chat)
            requested_timeout = request_timeout(metadata)
            if requested_timeout is not None:
                if not _accepts_keyword(transport, "timeout_seconds"):
                    raise AdapterError("unsupported_timeout_transport")
                configured = getattr(client, "timeout", self.client_timeout) or requested_timeout
                kwargs["timeout_seconds"] = min(configured, requested_timeout)
            budget = current_budget()
            if budget is not None:
                if not _accepts_keyword(client.chat, "_attempt_budget") or not _accepts_keyword(transport, "_attempt_budget"):
                    raise AdapterError("unsupported_budget_transport", "transport lacks attempt reservation")
                call_budget = budget.model_call((metadata or {}).get("role"),
                                                solver_call_id=(metadata or {}).get("call_id"), deadline_at=scoped_deadline(metadata), strict_completion=(metadata or {}).get("strict_completion") is True)
                kwargs["_attempt_budget"] = call_budget
            if self.outbound_observer is not None:
                self.outbound_observer(normalized)
            raw = transport(normalized, **kwargs)
        except Exception as exc:  # noqa: BLE001 - provider details stay out of events
            source_attempts = tuple(getattr(exc, "attempts", ()))
            attempts = record_attempts(source_attempts, metadata)
            for source, projection in zip(source_attempts, attempts):
                if isinstance(source, dict):
                    bind_attempt_projection(source, projection)
            category = getattr(exc, "category", None) or (
                "configuration" if type(exc).__name__ == "ChatClientError" else "adapter_error"
            )
            error = AdapterError(str(category), type(exc).__name__)
            error.request_attempts = attempts
            raise error from exc
        def normalize_response():
            text, usage = _extract_response(raw)
            parsed = parse_tool_requests(
                text, raw.get("tool_calls") if isinstance(raw, Mapping) else None
            )
            return text, usage, parsed

        if budget is None:
            text, usage, parsed = normalize_response()
        else:
            from .processing_deadline import process_before_deadline

            source_attempts = raw.get("attempts", ()) if isinstance(raw, Mapping) else ()
            absolute = source_attempts[-1].get("deadline_at") if source_attempts else None
            remaining = call_budget.remaining_seconds()
            if isinstance(absolute, (int, float)):
                remaining = min(remaining, max(0, absolute - time.time()))
            try:
                text, usage, parsed = process_before_deadline(
                    normalize_response, time.monotonic() + remaining,
                    lambda _result, _error: None,
                )
            except requests.ReadTimeout as exc:
                error = AdapterError("timeout", "local_processing_deadline")
                error.request_attempts = record_attempts(source_attempts, metadata)
                raise error from exc
        attempts = record_attempts(raw.get("attempts", ()), metadata) if isinstance(raw, Mapping) else ()
        return ModelResponse(
            text=text,
            tool_requests=parsed.requests,
            usage=usage,
            request_attempts=attempts,
            returned_model=raw.get("model") if isinstance(raw, Mapping) else None,
            finish_reason=raw.get("finish_reason") if isinstance(raw, Mapping) else None,
            model_id=getattr(client, "model", self.model_id) or self.model_id,
            tool_protocol=parsed.protocol,
            tool_request_error=parsed.error_category,
        )

    def ensure_configured(self) -> None:
        """Raise ``AdapterError`` until a provider client can actually be built."""
        self._get_client()

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from llm_client import InternChatClient

            client_kwargs: dict[str, int] = {}
            if self.client_timeout is not None:
                client_kwargs["timeout"] = self.client_timeout
            if self.client_retry is not None:
                client_kwargs["retry"] = self.client_retry
            self._client = InternChatClient(**client_kwargs)
        except Exception as exc:  # noqa: BLE001 - missing credentials are expected locally
            category = getattr(exc, "category", None) or "configuration"
            raise AdapterError(str(category), type(exc).__name__) from exc
        return self._client


class InternStreamAdapter(InternModelAdapter):
    """Explicitly injected SSE-streaming variant; the default adapter stays non-streaming.

    ``stream_complete`` yields ``text_delta`` fragments as they arrive on the wire
    so the existing call audit persists each delta before the next provider
    fragment is requested. Outbound metering reserves through the same persisted
    run budget ledger as the non-streaming client path.
    """

    def stream_complete(self, messages, *, metadata=None):
        """Yield provider fragments, then exactly one complete result envelope."""
        client = self._get_client()
        if any(not isinstance(getattr(client, name, None), str) for name in ("api_base", "authorization")):
            raise AdapterError("stream_transport_unavailable")
        normalized = [_normalize_message(message) for message in messages]
        model_id = getattr(client, "model", None) or self.model_id
        thinking_mode = self.thinking_mode if self.thinking_mode is not None else getattr(client, "thinking_mode", None)
        payload = {
            "model": model_id, "messages": normalized, "stream": True,
            "temperature": self.temperature, "max_tokens": self.max_tokens,
        }
        if thinking_mode is not None:
            payload["thinking_mode"] = thinking_mode
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json", "Authorization": client.authorization}
        role = (metadata or {}).get("role")
        attempt = {
            "logical_call_id": uuid.uuid4().hex,
            "attempt_id": uuid.uuid4().hex,
            "attempt_index": 1,
            "request_model_id": model_id,
            "role": role,
            "solver_call_id": (metadata or {}).get("call_id"),
            "started_at_utc": datetime.now(UTC).isoformat(),
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "thinking_mode": thinking_mode,
            "request_purpose": (metadata or {}).get("purpose") or role or "model_response",
            "provider_stream": True,
            "requests_stream": True,
            "message_count": len(normalized),
            "response_headers_seconds": None,
            "first_byte_seconds": None,
            "first_event_seconds": None,
            "first_reasoning_seconds": None,
            "first_content_seconds": None,
            "completion_seconds": None,
            "reasoning_chars": 0,
            "content_bytes": 0,
            "event_count": 0,
            "status": "pending",
        }
        budget = current_budget()
        call_budget = budget.model_call(role, solver_call_id=attempt["solver_call_id"], deadline_at=scoped_deadline(metadata), strict_completion=(metadata or {}).get("strict_completion") is True) if budget else None
        configured = getattr(client, "timeout", self.client_timeout)
        requested = request_timeout(metadata)
        effective_timeout = configured or requested or 30
        if requested is not None:
            effective_timeout = min(configured or requested, requested)
        attempts: list[dict[str, Any]] = []
        response = None
        started = time.monotonic()
        logical_deadline = started + effective_timeout
        if call_budget is not None:
            logical_deadline = min(logical_deadline, started + call_budget.remaining_seconds())
        from llm_client import product_attempt_limit

        limit = product_attempt_limit(client) if call_budget else 1
        attempt.update(effective_timeout_seconds=effective_timeout, deadline_at=time.time() + max(0, logical_deadline - time.monotonic()))
        attempt["requests_timeout_seconds"] = configured or effective_timeout
        attempt["retry_limit"] = limit
        local_processing_timeout = False
        timeout_attempts = None
        late_state = None
        result = None
        try:
            from llm_client import _not_submitted, product_retry_delay

            from .request_transport import response_events
            for index in range(limit):
                attempt_started = time.monotonic()
                try:
                    remaining = logical_deadline - time.monotonic()
                    if remaining <= 0:
                        raise requests.ReadTimeout("logical_deadline_exceeded")
                    attempt_timeout = min(effective_timeout, remaining)
                    if call_budget is not None:
                        attempt_timeout = min(attempt_timeout, call_budget.before_attempt(attempt, len(body)))
                    attempt["effective_timeout_seconds"] = attempt_timeout

                    late_state = {"lock": threading.Lock(), "event": None}

                    def settle_late(response, raw_body, headers_seconds, completion_seconds,
                                    body_complete=True, late_snapshot=dict(attempt), late_state=late_state):
                        late_attempt = dict(late_snapshot)
                        late_usage = {}
                        late_finish = None
                        late_model = None
                        late_reasoning_chars = 0
                        late_content_bytes = 0
                        late_event_count = 0
                        late_done = False
                        late_invalid = False
                        for raw_line in raw_body.splitlines():
                            line = raw_line.decode("utf-8", errors="replace").strip()
                            if not line.startswith("data:"):
                                continue
                            late_event_count += 1
                            if line[len("data:"):].strip() == "[DONE]":
                                late_done = True
                                continue
                            try:
                                late_chunk = json.loads(line[len("data:"):].strip())
                            except ValueError:
                                late_invalid = True
                                continue
                            choices = late_chunk.get("choices")
                            choice = choices[0] if isinstance(choices, list) and choices else {}
                            delta = choice.get("delta") if isinstance(choice, Mapping) else None
                            if isinstance(delta, Mapping):
                                reasoning = delta.get("reasoning_content")
                                content = delta.get("content")
                                if isinstance(reasoning, str):
                                    late_reasoning_chars += len(reasoning)
                                if isinstance(content, str):
                                    late_content_bytes += len(content.encode("utf-8"))
                            if isinstance(choice.get("finish_reason"), str):
                                late_finish = choice["finish_reason"]
                            if isinstance(late_chunk.get("model"), str):
                                late_model = late_chunk["model"]
                            if isinstance(late_chunk.get("usage"), Mapping):
                                late_usage.update(late_chunk["usage"])
                        http_success = type(response.status_code) is int and 200 <= response.status_code < 300
                        strict = (metadata or {}).get("strict_completion") is True
                        if not late_usage and not (body_complete or not http_success or late_invalid):
                            return
                        if not http_success:
                            missing = "http_status"
                        elif late_invalid:
                            missing = "invalid_response"
                        elif body_complete and not late_done:
                            missing = "missing_stream_terminal" if strict else "connectivity"
                        elif body_complete and strict and late_finish is None:
                            missing = "missing_finish_reason"
                        else:
                            missing = None
                        late_attempt.update(
                            status="unknown" if not body_complete and http_success else "error" if missing else "success",
                            error_category=missing if missing else None,
                            http_status=response.status_code,
                            response_headers_seconds=headers_seconds,
                            completion_seconds=completion_seconds,
                            response_model_id=late_model,
                            finish_reason=late_finish,
                            reasoning_chars=late_reasoning_chars,
                            content_bytes=late_content_bytes,
                            event_count=late_event_count,
                            **{key: late_usage.get(key) for key in
                               ("prompt_tokens", "completion_tokens", "total_tokens")},
                        )
                        if call_budget is not None:
                            from .run_budget_late import settle_late_with_retry

                            with late_state["lock"]:
                                settle_late_with_retry(call_budget, late_attempt)
                                late_state["event"] = late_attempt

                    if self.outbound_observer is not None:
                        self.outbound_observer(normalized)
                    line_buffer = bytearray()
                    parts: list[str] = []
                    usage: dict[str, Any] = {}
                    finish_reason = None
                    saw_done = False

                    def parse_line(raw_line, late_state=late_state):
                        nonlocal finish_reason, model_id, saw_done
                        line = raw_line.decode("utf-8", errors="replace").strip()
                        if not line.startswith("data:"):
                            return
                        content = line[len("data:"):].strip()
                        attempt["event_count"] += 1
                        if attempt["first_event_seconds"] is None:
                            attempt["first_event_seconds"] = time.monotonic() - attempt_started
                        if content == "[DONE]":
                            saw_done = True
                            return
                        try:
                            if call_budget is None:
                                chunk = json.loads(content)
                            else:
                                from .processing_deadline import process_before_deadline

                                partial_snapshot = dict(attempt)

                                def settle_partial(parsed, error):
                                    if error is not None or not isinstance(parsed, Mapping):
                                        return
                                    known_usage = parsed.get("usage")
                                    if not isinstance(known_usage, Mapping):
                                        return
                                    from .run_budget_late import settle_late_with_retry

                                    with late_state["lock"]:
                                        partial = dict(late_state["event"] or {
                                            **partial_snapshot, "status": "unknown",
                                            "error_category": "timeout",
                                        })
                                        partial.update({key: known_usage.get(key) for key in
                                                        ("prompt_tokens", "completion_tokens", "total_tokens")})
                                        settle_late_with_retry(call_budget, partial)

                                try:
                                    chunk = process_before_deadline(
                                        lambda: json.loads(content), logical_deadline, settle_partial,
                                    )
                                except requests.ReadTimeout:
                                    transport_events.close()
                                    raise
                        except ValueError as exc:
                            raise AdapterError("invalid_response", "invalid_sse_chunk") from exc
                        choices = chunk.get("choices")
                        choice = choices[0] if isinstance(choices, list) and choices else {}
                        delta = choice.get("delta") if isinstance(choice, Mapping) else None
                        reasoning = delta.get("reasoning_content") if isinstance(delta, Mapping) else None
                        piece = delta.get("content") if isinstance(delta, Mapping) else None
                        if isinstance(reasoning, str) and reasoning:
                            if attempt["first_reasoning_seconds"] is None:
                                attempt["first_reasoning_seconds"] = time.monotonic() - attempt_started
                            attempt["reasoning_chars"] += len(reasoning)
                        if isinstance(piece, str) and piece:
                            if attempt["first_content_seconds"] is None:
                                attempt["first_content_seconds"] = time.monotonic() - attempt_started
                            parts.append(piece)
                            attempt["content_bytes"] += len(piece.encode("utf-8"))
                            yield_piece = {"type": "text_delta", "text": piece}
                            pending_chunks.append(yield_piece)
                        if isinstance(choice.get("finish_reason"), str):
                            finish_reason = choice["finish_reason"]
                        if isinstance(chunk.get("model"), str):
                            model_id = chunk["model"]
                        if isinstance(chunk.get("usage"), Mapping):
                            usage.update(chunk["usage"])

                    pending_chunks = []
                    stream_complete = False

                    def check_processing_deadline():
                        nonlocal local_processing_timeout
                        if time.monotonic() < logical_deadline:
                            return
                        attempt.update({key: usage.get(key) for key in ("prompt_tokens", "completion_tokens", "total_tokens")})
                        if stream_complete and saw_done and (not (metadata or {}).get("strict_completion") or finish_reason is not None):
                            attempt.update(status="success", finish_reason=finish_reason, response_model_id=model_id)
                            local_processing_timeout = True
                        raise requests.ReadTimeout("logical_deadline_exceeded_during_processing")

                    transport_events = response_events(
                        client.api_base,
                        headers=headers,
                        data=body,
                        deadline=logical_deadline,
                        timeout=configured or effective_timeout,
                        loopback_only=getattr(client, "loopback_only", False),
                        provider_endpoint_only=getattr(client, "provider_endpoint_only", False),
                        on_late_response=settle_late,
                    )
                    for kind, value in transport_events:
                        if kind == "headers":
                            response = value
                            attempt["http_status"] = response.status_code
                            attempt["response_headers_seconds"] = time.monotonic() - attempt_started
                            response.raise_for_status()
                        elif kind == "bytes":
                            if attempt["first_byte_seconds"] is None:
                                attempt["first_byte_seconds"] = time.monotonic() - attempt_started
                            line_buffer.extend(value)
                            while b"\n" in line_buffer:
                                line, _, remainder = line_buffer.partition(b"\n")
                                line_buffer = bytearray(remainder)
                                parse_line(line)
                                check_processing_deadline()
                                for delta_chunk in pending_chunks:
                                    yield delta_chunk
                                    check_processing_deadline()
                                pending_chunks.clear()
                        elif kind == "complete":
                            stream_complete = True
                            attempt["completion_seconds"] = time.monotonic() - attempt_started
                    if line_buffer:
                        parse_line(line_buffer)
                        check_processing_deadline()
                        for delta_chunk in pending_chunks:
                            yield delta_chunk
                            check_processing_deadline()
                    check_processing_deadline()
                    if (metadata or {}).get("strict_completion") is True and stream_complete and (not saw_done or finish_reason is None):
                        attempt.update({key: usage.get(key) for key in ("prompt_tokens", "completion_tokens", "total_tokens")})
                        raise AdapterError("missing_stream_terminal" if not saw_done else "missing_finish_reason")
                    if not stream_complete or not saw_done:
                        raise requests.ConnectionError("incomplete_stream")
                    break
                except requests.RequestException as failure:
                    if response is None and getattr(failure, "response", None) is not None:
                        response = failure.response
                        attempt["http_status"] = getattr(response, "status_code", None)
                    delay = product_retry_delay(failure, response, index, call_budget) if call_budget else None
                    if call_budget and _not_submitted(failure):
                        attempt.update(status="not_submitted", prompt_tokens=0,
                                       completion_tokens=0, total_tokens=0)
                    elif not local_processing_timeout:
                        attempt.update(status="error")
                    if delay is None or index + 1 >= limit:
                        raise
                    attempt.update(error_category=_request_failure_category(failure),
                                   error_type=type(failure).__name__,
                                   http_status=getattr(response, "status_code", None),
                                   duration_seconds=round(time.monotonic() - attempt_started, 3))
                    attempts.append(dict(attempt))
                    call_budget.after_attempt(attempt)
                    response = None
                    if time.monotonic() + delay >= logical_deadline:
                        raise
                    if not call_budget.can_retry(delay, len(body), self.max_tokens):
                        raise
                    time.sleep(delay)
                    attempt = {**attempt, "attempt_id": uuid.uuid4().hex,
                               "attempt_index": index + 2, "status": "pending",
                               "started_at_utc": datetime.now(UTC).isoformat()}
                    for key in (
                        "response_headers_seconds", "first_byte_seconds", "first_event_seconds",
                        "first_reasoning_seconds", "first_content_seconds", "completion_seconds",
                    ):
                        attempt[key] = None
                    attempt.update(event_count=0, reasoning_chars=0, content_bytes=0)
                    for key in ("prompt_tokens", "completion_tokens", "total_tokens",
                                "error_category", "error_type", "http_status"):
                        attempt.pop(key, None)
                    attempt["effective_timeout_seconds"] = min(effective_timeout, logical_deadline - time.monotonic())
            attempt.update(status="success", http_status=getattr(response, "status_code", None))
            attempt.update(
                finish_reason=finish_reason,
                response_model_id=model_id,
                **{key: usage.get(key) for key in ("prompt_tokens", "completion_tokens", "total_tokens")},
            )
            attempt["duration_seconds"] = round(time.monotonic() - attempt_started, 3)
            attempts.append(dict(attempt))
            def assemble_result():
                projection_metadata = {**(metadata or {}), "run_id": call_budget.run_id} if call_budget else metadata
                return {
                    "type": "result",
                    "text": "".join(parts),
                    "usage": usage,
                    "finish_reason": finish_reason,
                    "model": model_id,
                    "attempts": record_attempts(attempts, projection_metadata),
                }

            if call_budget is None:
                result = assemble_result()
            else:
                from .processing_deadline import process_before_deadline
                from .request_attempts import publish_attempts

                try:
                    result = process_before_deadline(
                        assemble_result, logical_deadline, lambda _result, _error: None
                    )
                except requests.ReadTimeout:
                    from llm_response import public_attempt

                    local_processing_timeout = True
                    timeout_attempts = (public_attempt(attempt, run_id=call_budget.run_id,
                                                       role=(metadata or {}).get("role")),)
                    publish_attempts(timeout_attempts)
                    raise
                publish_attempts(result["attempts"])
            check_processing_deadline()
            yield result
        except AdapterError as exc:
            attempt.update(status="error", error_category=exc.category, error_type=type(exc).__name__)
            attempt["duration_seconds"] = round(time.monotonic() - attempt_started, 3)
            attempts.append(dict(attempt))
            exc.request_attempts = record_attempts(attempts, metadata)
            raise
        except Exception as exc:  # noqa: BLE001 - provider details stay out of events
            category = _request_failure_category(exc)
            from llm_client import _not_submitted
            if not local_processing_timeout:
                attempt.update(status="not_submitted" if _not_submitted(exc) else "error",
                               error_category=category, error_type=type(exc).__name__)
            attempt["duration_seconds"] = round(time.monotonic() - attempt_started, 3)
            if attempts and attempts[-1].get("attempt_id") == attempt.get("attempt_id"):
                attempts[-1] = dict(attempt)
            else:
                attempts.append(dict(attempt))
            error = AdapterError(category, type(exc).__name__)
            error.request_attempts = (timeout_attempts if timeout_attempts is not None else
                                      result["attempts"] if local_processing_timeout and result is not None
                                      else record_attempts(attempts, metadata))
            raise error from exc
        finally:
            attempt["duration_seconds"] = round(time.monotonic() - attempt_started, 3)
            if not attempts:
                attempts.append(dict(attempt))
            if call_budget is not None:
                # Never wait for a late settlement: if it owns the gate, it will
                # either persist its evidence or leave the original reservation.
                if late_state is None:
                    call_budget.after_attempt(attempt)
                elif late_state["lock"].acquire(blocking=False):
                    try:
                        if late_state["event"] is None:
                            if (attempt.get("error_category") == "timeout"
                                    and attempt.get("status") != "not_submitted") or local_processing_timeout:
                                from .run_budget_late import settle_timeout_nonblocking

                                settle_timeout_nonblocking(call_budget, attempt)
                            else:
                                call_budget.after_attempt(attempt)
                    finally:
                        late_state["lock"].release()


def _request_failure_category(exc: BaseException) -> str:
    if isinstance(exc, requests.Timeout):
        return "timeout"
    if isinstance(exc, requests.exceptions.ProxyError):
        return "proxy"
    if isinstance(exc, requests.exceptions.SSLError):
        return "tls"
    if isinstance(exc, requests.ConnectionError):
        return "connectivity"
    if isinstance(exc, requests.exceptions.ChunkedEncodingError):
        return "connectivity"
    if isinstance(exc, requests.HTTPError):
        return "http_status"
    if isinstance(exc, requests.RequestException):
        return "request"
    return "adapter_error"


class InternAgentAdapter:
    """Role-level adapter that converts model responses into graph decisions."""

    def __init__(
        self,
        model: InternModelAdapter,
        *,
        role: str = "solver",
        tool_schemas: Sequence[Mapping[str, Any]] = (),
        continuation_transport: ContinuationTransport | None = None,
    ) -> None:
        self.model = model
        self.role = role
        self.tool_schemas = tuple(dict(schema) for schema in tool_schemas)
        self.continuation_transport = continuation_transport or ModelContinuationTransport(model)

    def decide(self, state: Mapping[str, Any]) -> AgentDecision:
        """Ask Intern for one bounded decision using product-level state only."""

        problem = str(state.get("problem", ""))
        messages = [
            {
                "role": "system",
                "content": (
                    f"You are the {self.role} role. Return a concise final answer, or a JSON "
                    "tool_call object when registered computation is required."
                ),
            },
            {"role": "user", "content": problem},
        ]
        transport_mode = "live"
        try:
            previous = state.get("tool_results")
            if isinstance(previous, Sequence) and previous and isinstance(previous[-1], Mapping):
                last = previous[-1]
                request = ToolRequest(
                    str(last.get("name", "")),
                    last.get("arguments", {}) if isinstance(last.get("arguments"), Mapping) else {},
                    tool_call_id=str(last.get("tool_call_id", last.get("request_id", ""))),
                    protocol=last.get("protocol", "text_action"),
                )
                response = self.continuation_transport.continue_(messages, request, last)
                transport_mode = getattr(self.continuation_transport, "mode", "unavailable")
                summary_prefix = f"continuation transport={transport_mode}"
            else:
                response = self.model.complete(messages, tools=self.tool_schemas)
                summary_prefix = "model"
        except AdapterError as exc:
            return AgentDecision.failure(
                f"Intern adapter unavailable: {exc.category}",
                error_category=exc.category,
            )
        if response.tool_request_error:
            return AgentDecision.review(
                "Intern tool request could not be parsed",
                response.tool_request_error,
            )
        if response.tool_requests:
            if len(response.tool_requests) != 1:
                return AgentDecision.review("Intern requested multiple tools", "multiple_tool_requests")
            request = response.tool_requests[0]
            if request.error_category:
                return AgentDecision.review("Intern tool request is invalid", request.error_category)
            return AgentDecision.tool(request.name, request.arguments, summary="Intern requested a tool")
        if not response.text.strip():
            return AgentDecision.failure("Intern returned an empty response", "empty_model_response")
        return AgentDecision(
            kind="final",
            final_response=response.text,
            summary=f"{summary_prefix}={response.model_id}",
            transport_mode=(transport_mode if summary_prefix.startswith("continuation") else "live"),
        )

    def run(self, request: RunRequest) -> AgentResult:
        """Provide the RunService AgentAdapter shape for a single model turn."""

        decision = self.decide({"problem": request.problem})
        if decision.kind == "final":
            return AgentResult(final_response=decision.final_response, summary=decision.summary)
        if decision.kind == "tool":
            raise AdapterError("tool_request_requires_execution", decision.tool_name)
        raise AdapterError(decision.error_category, decision.summary)


class InternChatModel:
    """Small LangChain ``BaseChatModel`` bridge used by DeepAgents."""

    def __new__(cls, *args: Any, **kwargs: Any) -> Any:
        try:
            from langchain_core.language_models import BaseChatModel
            from langchain_core.messages import AIMessage
            from langchain_core.outputs import ChatGeneration, ChatResult
            from pydantic import ConfigDict
        except ImportError as exc:  # pragma: no cover - product dependency boundary
            raise AdapterError("showcase_dependency_missing", "langchain-core") from exc

        class _InternChatModel(BaseChatModel):
            model_config = ConfigDict(arbitrary_types_allowed=True)
            client: Any
            model_id: str = "intern-s2"
            bound_tools: tuple[Any, ...] = ()

            @property
            def _llm_type(self) -> str:
                return "intern-showcase"

            def _generate(self, messages: Sequence[Any], stop: Sequence[str] | None = None,
                          run_manager: Any = None, **kwargs: Any) -> Any:
                payload = [
                    {"role": _message_role(message), "content": _message_content(message)}
                    for message in messages
                ]
                text = self.client.chat(payload, temperature=0.2, max_tokens=16_384)
                text = str(text)
                requests = parse_tool_requests(text).requests
                if requests:
                    message = AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": request.name,
                                "args": dict(request.arguments),
                                "id": request.tool_call_id or f"call_{index}",
                            }
                            for index, request in enumerate(requests, 1)
                            if request.error_category is None
                        ],
                    )
                    if not message.tool_calls:
                        message = AIMessage(content=text)
                else:
                    message = AIMessage(content=text)
                return ChatResult(generations=[ChatGeneration(message=message)])

            def bind_tools(self, tools: Sequence[Any], *, tool_choice: str | None = None,
                           **kwargs: Any) -> Any:
                return self.model_copy(update={"bound_tools": tuple(tools)})

        return _InternChatModel(client=args[0], model_id=kwargs.get("model_id", "intern-s2"))


class DeepAgentsAdapter:
    """Use DeepAgents behind the product AgentAdapter boundary."""

    def __init__(
        self,
        client: Any,
        *,
        tools: Sequence[Callable[..., Any]] = (),
        system_prompt: str = "Solve the math problem and return a concise answer.",
        model_id: str = "intern-s2",
    ) -> None:
        try:
            from deepagents import create_deep_agent
        except ImportError as exc:  # pragma: no cover - product dependency boundary
            raise AdapterError("showcase_dependency_missing", "deepagents") from exc
        self._agent = create_deep_agent(
            model=InternChatModel(client, model_id=model_id),
            tools=[_prepare_deep_tool(tool) for tool in tools],
            system_prompt=system_prompt,
        )

    def run(self, request: RunRequest) -> AgentResult:
        """Invoke DeepAgents and convert its final message into a product result."""

        try:
            result = self._agent.invoke({"messages": [{"role": "user", "content": request.problem}]})
        except Exception as exc:  # noqa: BLE001 - framework details stay behind adapter
            raise AdapterError("deepagents_error", type(exc).__name__) from exc
        text = _extract_agent_text(result)
        if not text:
            raise AdapterError("empty_agent_response")
        return AgentResult(final_response=text, summary="deepagents role adapter")


def _normalize_message(message: Mapping[str, Any]) -> dict[str, Any]:
    role = message.get("role")
    content = message.get("content")
    if not isinstance(role, str) or not isinstance(content, (str, list, tuple, type(None))):
        raise AdapterError("message_invalid")
    normalized = {"role": role, "content": content}
    tool_calls = message.get("tool_calls")
    if tool_calls is not None:
        if not isinstance(tool_calls, Sequence) or isinstance(tool_calls, (str, bytes)):
            raise AdapterError("message_invalid")
        normalized["tool_calls"] = [dict(call) for call in tool_calls if isinstance(call, Mapping)]
    for key in ("tool_call_id", "name"):
        value = message.get(key)
        if value is not None:
            if not isinstance(value, str):
                raise AdapterError("message_invalid")
            normalized[key] = value
    return normalized


def _prepare_deep_tool(tool: Callable[..., Any]) -> Callable[..., Any]:
    """Give anonymous injected callables the description DeepAgents requires."""

    if getattr(tool, "__doc__", None):
        return tool

    @wraps(tool)
    def described_tool(*args: Any, **kwargs: Any) -> Any:
        return tool(*args, **kwargs)

    described_tool.__doc__ = f"Registered showcase tool: {getattr(tool, '__name__', 'tool')}"
    return described_tool


def _extract_response(raw: Any) -> tuple[str, dict[str, Any]]:
    if isinstance(raw, str):
        return raw, {}
    if isinstance(raw, Mapping):
        content = raw.get("content", raw.get("text", ""))
        usage = raw.get("usage") if isinstance(raw.get("usage"), Mapping) else {}
        return content if isinstance(content, str) else "", dict(usage)
    return str(raw), {}


def _accepts_keyword(function: Callable[..., Any], name: str) -> bool:
    try:
        import inspect

        parameters = inspect.signature(function).parameters
        return name in parameters or any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()
        )
    except (TypeError, ValueError):
        return False


def _message_role(message: Any) -> str:
    role = getattr(message, "type", None)
    return {"human": "user", "ai": "assistant", "system": "system", "tool": "tool"}.get(
        role, "user"
    )


def _message_content(message: Any) -> Any:
    content = getattr(message, "content", "")
    if isinstance(content, (str, list, tuple)):
        return content
    return str(content)


def _extract_agent_text(result: Any) -> str:
    if isinstance(result, Mapping):
        direct = result.get("final_response")
        if isinstance(direct, str):
            return direct
        messages = result.get("messages")
        if isinstance(messages, Sequence):
            for message in reversed(messages):
                content = _message_content(message)
                if isinstance(content, str) and content.strip():
                    return content
    return ""


__all__ = [
    "AdapterError",
    "ContinuationTransport",
    "DeepAgentsAdapter",
    "InternAgentAdapter",
    "InternChatModel",
    "InternModelAdapter",
    "InternStreamAdapter",
    "ModelResponse",
    "ModelContinuationTransport",
    "ToolRequest",
]
