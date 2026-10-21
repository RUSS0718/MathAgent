"""Provider-neutral tool call types and explicit protocol parsing."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

ToolProtocol = Literal["native", "text_action"]


@dataclass(frozen=True)
class ToolRequest:
    """One parsed model request with its provider call identity and protocol."""

    name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    tool_call_id: str = ""
    protocol: ToolProtocol = "text_action"
    assistant_content: str = ""
    error_category: str | None = None


@dataclass(frozen=True)
class ParsedToolRequests:
    """Explicit result of parsing either supported tool protocol."""

    protocol: ToolProtocol | None = None
    requests: tuple[ToolRequest, ...] = ()
    error_category: str | None = None


def parse_tool_requests(text: str, native_calls: Any = None) -> ParsedToolRequests:
    """Parse native function calls or the explicitly tagged text action envelope."""

    native_present = native_calls is not None
    text_payload: Mapping[str, Any] | None = None
    try:
        candidate = text.strip()
        if candidate.startswith("```"):
            candidate = candidate.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        decoded = json.loads(candidate)
        if isinstance(decoded, Mapping):
            text_payload = decoded
    except (TypeError, ValueError):
        if '"tool_call"' in text or '"tool_calls"' in text:
            return ParsedToolRequests("text_action", error_category="tool_request_invalid")

    text_has_calls = bool(
        text_payload is not None
        and ("tool_call" in text_payload or "tool_calls" in text_payload)
    )
    native_has_calls = native_present and native_calls != []
    if native_has_calls and text_has_calls:
        return ParsedToolRequests(error_category="tool_protocol_mixed")
    if native_has_calls:
        if not isinstance(native_calls, Sequence) or isinstance(native_calls, (str, bytes)):
            return ParsedToolRequests("native", error_category="tool_request_invalid")
        requests = tuple(_native_request(call) for call in native_calls)
        return ParsedToolRequests("native", requests)
    if text_has_calls:
        assert text_payload is not None
        if text_payload.get("protocol") != "text_action":
            return ParsedToolRequests("text_action", error_category="tool_protocol_missing")
        raw_calls = text_payload.get("tool_calls", text_payload.get("tool_call"))
        if isinstance(raw_calls, Mapping):
            raw_calls = [raw_calls]
        if not isinstance(raw_calls, Sequence) or isinstance(raw_calls, (str, bytes)):
            return ParsedToolRequests("text_action", error_category="tool_request_invalid")
        if not raw_calls:
            return ParsedToolRequests("text_action", error_category="tool_request_invalid")
        requests = tuple(_text_request(call, text) for call in raw_calls)
        return ParsedToolRequests("text_action", requests)
    return ParsedToolRequests()


def _native_request(call: Any) -> ToolRequest:
    if not isinstance(call, Mapping):
        return ToolRequest("", {}, protocol="native", error_category="tool_request_invalid")
    tool_call_id = call.get("id")
    if not isinstance(tool_call_id, str) or not tool_call_id.strip():
        tool_call_id = ""
        id_error = "tool_call_id_missing"
    else:
        id_error = None
    function = call.get("function")
    if not isinstance(function, Mapping):
        return ToolRequest(
            "", {}, tool_call_id, protocol="native", error_category="tool_request_invalid"
        )
    name = function.get("name")
    raw_arguments = function.get("arguments")
    arguments, error = _arguments(raw_arguments)
    if call.get("type") != "function":
        error = "tool_request_invalid"
    if not isinstance(name, str) or not name:
        error = error or "tool_request_invalid"
    error = error or id_error
    return ToolRequest(
        name=name if isinstance(name, str) else "",
        arguments=arguments,
        tool_call_id=tool_call_id,
        protocol="native",
        error_category=error,
    )


def _text_request(call: Any, assistant_content: str) -> ToolRequest:
    if not isinstance(call, Mapping):
        return ToolRequest(
            "", {}, protocol="text_action", assistant_content=assistant_content,
            error_category="tool_request_invalid",
        )
    name = call.get("name")
    raw_arguments = call.get("arguments")
    arguments, error = _arguments(raw_arguments)
    tool_call_id = call.get("tool_call_id", call.get("id"))
    if not isinstance(name, str) or not name:
        error = error or "tool_request_invalid"
    if not isinstance(tool_call_id, str) or not tool_call_id.strip():
        error = error or "tool_call_id_missing"
        tool_call_id = ""
    return ToolRequest(
        name=name if isinstance(name, str) else "",
        arguments=arguments,
        tool_call_id=tool_call_id,
        protocol="text_action",
        assistant_content=assistant_content,
        error_category=error,
    )


def _arguments(value: Any) -> tuple[Mapping[str, Any], str | None]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return {}, "tool_arguments_invalid"
    if not isinstance(value, Mapping):
        return {}, "tool_arguments_invalid"
    return dict(value), None


__all__ = ["ParsedToolRequests", "ToolProtocol", "ToolRequest", "parse_tool_requests"]
