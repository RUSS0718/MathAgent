"""Request-scoped provider response and public metering normalization."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any

USAGE_FIELDS = (
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "reasoning_tokens",
    "cached_tokens",
)


def provider_usage(raw: Any) -> dict[str, int | None]:
    usage = raw if isinstance(raw, Mapping) else {}
    result = {key: _count(usage.get(key)) for key in USAGE_FIELDS[:3]}
    completion = usage.get("completion_tokens_details")
    prompt = usage.get("prompt_tokens_details")
    result["reasoning_tokens"] = (
        _count(completion.get("reasoning_tokens")) if isinstance(completion, Mapping) else None
    )
    result["cached_tokens"] = (
        _count(prompt.get("cached_tokens")) if isinstance(prompt, Mapping) else None
    )
    return result


def _count(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def safe_identifier(value: Any) -> str | None:
    return (
        value
        if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:/-]{1,160}", value)
        else None
    )


def public_attempt(
    event: Mapping[str, Any], *, run_id: str | None = None, role: str | None = None
) -> dict[str, Any]:
    source = event.get("usage") if isinstance(event.get("usage"), Mapping) else event
    usage = {key: _count(source.get(key)) for key in USAGE_FIELDS}
    return {
        "attempt_id": safe_identifier(event.get("attempt_id")),
        "logical_call_id": safe_identifier(event.get("logical_call_id")),
        "run_id": safe_identifier(run_id),
        "role": safe_identifier(role),
        "action": safe_identifier(role),
        "attempt_index": _count(event.get("attempt_index")),
        "started_at_utc": event.get("started_at_utc") if isinstance(event.get("started_at_utc"), str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}T[0-9:.]+(?:Z|[+-]\d{2}:\d{2})", event["started_at_utc"]) else None,
        "dispatch_status": event.get("dispatch_status") if event.get("dispatch_status") in {"reserved_dispatch_unconfirmed", "transport_observed"} else None,
        "requested_model": safe_identifier(
            event.get("request_model_id", event.get("requested_model"))
        ),
        "returned_model": safe_identifier(
            event.get("response_model_id", event.get("returned_model"))
        ),
        "provider_request_id": safe_identifier(
            event.get("response_id", event.get("provider_request_id"))
        ),
        "finish_reason": safe_identifier(event.get("finish_reason")),
        "status": event.get("status") if event.get("status") in {"success", "error"} else "unknown",
        "http_status": _count(event.get("http_status")),
        "duration_seconds": _duration(event.get("duration_seconds")),
        "error_category": safe_identifier(event.get("error_category")),
        "stop_category": safe_identifier(event.get("error_category"))
        or {
            "stop": "completed",
            "length": "output_limit",
            "tool_calls": "tool_request",
            "content_filter": "content_filtered",
        }.get(event.get("finish_reason"), "unknown"),
        "usage": usage,
        "usage_source": "provider"
        if any(value is not None for value in usage.values())
        else "missing",
        "metering_status": "known"
        if all(usage[key] is not None for key in USAGE_FIELDS[:3])
        else "unknown",
        "thinking_mode": event.get("thinking_mode")
        if type(event.get("thinking_mode")) is bool
        else None,
        "temperature": event.get("temperature")
        if type(event.get("temperature")) in {int, float} and math.isfinite(event.get("temperature"))
        else None,
        "max_tokens": _count(event.get("max_tokens")),
        "request_purpose": safe_identifier(event.get("request_purpose")),
        "effective_timeout_seconds": _duration(event.get("effective_timeout_seconds")),
        "requests_timeout_seconds": _duration(event.get("requests_timeout_seconds")),
        "retry_limit": _count(event.get("retry_limit")),
        "response_headers_seconds": _duration(event.get("response_headers_seconds")),
        "first_byte_seconds": _duration(event.get("first_byte_seconds")),
        "first_event_seconds": _duration(event.get("first_event_seconds")),
        "first_reasoning_seconds": _duration(event.get("first_reasoning_seconds")),
        "first_content_seconds": _duration(event.get("first_content_seconds")),
        "completion_seconds": _duration(event.get("completion_seconds")),
        "reasoning_chars": _count(event.get("reasoning_chars")),
        "content_bytes": _count(event.get("content_bytes")),
        "event_count": _count(event.get("event_count")),
        "provider_stream": event.get("provider_stream")
        if type(event.get("provider_stream")) is bool
        else None,
        "requests_stream": event.get("requests_stream")
        if type(event.get("requests_stream")) is bool
        else None,
        "cost": None,
    }


def _duration(value):
    return value if type(value) in {int, float} and math.isfinite(value) and value >= 0 else None
