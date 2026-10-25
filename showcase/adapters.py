"""Product-level Intern and DeepAgents adapters.

The adapters normalize provider/framework behavior before it reaches Run state.
They are imported only by the explicit showcase profile and are safe to test
with an injected fake client.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import wraps
from typing import Any, Protocol

import requests

from .graph import AgentDecision
from .request_attempts import record_attempts
from .run_budget import current_budget
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
    ) -> None:
        self._client = client
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
        try:
            transport = getattr(client, "chat_response", client.chat)
            requested_timeout = (metadata or {}).get("timeout_seconds")
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
                                                solver_call_id=(metadata or {}).get("call_id"))
                kwargs["_attempt_budget"] = call_budget
            raw = transport(normalized, **kwargs)
        except Exception as exc:  # noqa: BLE001 - provider details stay out of events
            attempts = record_attempts(getattr(exc, "attempts", ()), metadata)
            category = getattr(exc, "category", None) or (
                "configuration" if type(exc).__name__ == "ChatClientError" else "adapter_error"
            )
            error = AdapterError(str(category), type(exc).__name__)
            error.request_attempts = attempts
            raise error from exc
        text, usage = _extract_response(raw)
        parsed = parse_tool_requests(
            text, raw.get("tool_calls") if isinstance(raw, Mapping) else None
        )
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
        body = json.dumps({
            "model": model_id, "messages": normalized, "stream": True,
            "temperature": self.temperature, "max_tokens": self.max_tokens,
        }, ensure_ascii=False).encode("utf-8")
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
            "message_count": len(normalized),
            "status": "pending",
        }
        budget = current_budget()
        call_budget = budget.model_call(role, solver_call_id=attempt["solver_call_id"]) if budget else None
        configured = getattr(client, "timeout", self.client_timeout)
        requested = (metadata or {}).get("timeout_seconds")
        effective_timeout = configured or requested or 30
        if requested is not None:
            effective_timeout = min(configured or requested, requested)
        attempts: list[dict[str, Any]] = []
        response = None
        started = time.monotonic()
        try:
            if call_budget is not None:
                effective_timeout = min(
                    effective_timeout, call_budget.before_attempt(attempt, len(body)))
            response = requests.post(
                client.api_base, headers=headers, data=body,
                timeout=effective_timeout, stream=True,
            )
            response.raise_for_status()
            attempt.update(status="success", http_status=getattr(response, "status_code", None))
            parts: list[str] = []
            usage: dict[str, Any] = {}
            finish_reason = None
            for line in response.iter_lines(decode_unicode=True):
                if not isinstance(line, str):
                    continue
                payload = line.strip()
                if not payload.startswith("data:"):
                    continue
                chunk_text = payload[len("data:"):].strip()
                if chunk_text == "[DONE]":
                    break
                try:
                    chunk = json.loads(chunk_text)
                except ValueError as exc:
                    raise AdapterError("invalid_response", "invalid_sse_chunk") from exc
                choice = chunk.get("choices")[0] if isinstance(chunk.get("choices"), list) and chunk["choices"] else {}
                delta = choice.get("delta") if isinstance(choice, Mapping) else None
                piece = delta.get("content") if isinstance(delta, Mapping) else None
                if isinstance(piece, str) and piece:
                    parts.append(piece)
                    yield {"type": "text_delta", "text": piece}
                if isinstance(choice.get("finish_reason"), str):
                    finish_reason = choice["finish_reason"]
                if isinstance(chunk.get("model"), str):
                    model_id = chunk["model"]
                if isinstance(chunk.get("usage"), Mapping):
                    usage = dict(chunk["usage"])
            attempt.update(
                finish_reason=finish_reason,
                response_model_id=model_id,
                **{key: usage.get(key) for key in ("prompt_tokens", "completion_tokens", "total_tokens")},
            )
            attempt["duration_seconds"] = round(time.monotonic() - started, 3)
            attempts.append(dict(attempt))
            yield {
                "type": "result",
                "text": "".join(parts),
                "usage": usage,
                "finish_reason": finish_reason,
                "model": model_id,
                "attempts": record_attempts(attempts, metadata),
            }
        except AdapterError as exc:
            attempt.update(status="error", error_category=exc.category, error_type=type(exc).__name__)
            attempt["duration_seconds"] = round(time.monotonic() - started, 3)
            attempts.append(dict(attempt))
            exc.request_attempts = record_attempts(attempts, metadata)
            raise
        except Exception as exc:  # noqa: BLE001 - provider details stay out of events
            category = _request_failure_category(exc)
            attempt.update(status="error", error_category=category, error_type=type(exc).__name__)
            attempt["duration_seconds"] = round(time.monotonic() - started, 3)
            attempts.append(dict(attempt))
            error = AdapterError(category, type(exc).__name__)
            error.request_attempts = record_attempts(attempts, metadata)
            raise error from exc
        finally:
            attempt["duration_seconds"] = round(time.monotonic() - started, 3)
            if not attempts:
                attempts.append(dict(attempt))
            if call_budget is not None:
                call_budget.after_attempt(attempt)
            if response is not None:
                response.close()


def _request_failure_category(exc: BaseException) -> str:
    if isinstance(exc, requests.Timeout):
        return "timeout"
    if isinstance(exc, requests.exceptions.ProxyError):
        return "proxy"
    if isinstance(exc, requests.exceptions.SSLError):
        return "tls"
    if isinstance(exc, requests.ConnectionError):
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
