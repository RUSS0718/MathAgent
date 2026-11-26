"""Bounded HTTP and response handling shared by Runtime chat adapters."""

import http.client
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import urlsplit

from ..port import ModelPortFailure, ModelReply


class ProviderConfigurationError(ValueError):
    """Report missing or malformed adapter configuration without exposing values."""


class ProviderPreflightError(ModelPortFailure):
    """Report a rejected request that was stopped before opening a connection."""

    failure_status = "preflight_rejected"
    request_sent = False


class ProviderHTTPError(ModelPortFailure):
    """Report a complete non-success HTTP response using only its status code."""

    failure_status = "protocol_failed"
    request_sent = True

    def __init__(self, status_code: int) -> None:
        """Retain a safe status code without response headers or body."""

        self.status_code = status_code
        super().__init__(f"provider returned HTTP status {status_code}")


class ProviderProtocolError(ModelPortFailure):
    """Report an invalid or over-limit successful provider response, redacted."""

    failure_status = "protocol_failed"
    request_sent = True

    def __init__(self, message: str, *, reply: "ChatCompletionReply | None" = None) -> None:
        self.reply = reply
        super().__init__(message)


class ProviderTimeoutError(ModelPortFailure, TimeoutError):
    """Report that the single provider request exceeded its transport timeout."""

    failure_status = "timeout"
    request_sent = "unknown"


class ProviderOutcomeUnknownError(ModelPortFailure, ConnectionError):
    """Report an interrupted request whose remote completion cannot be known."""

    failure_status = "unknown_outcome"
    request_sent = "unknown"


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    """Prevent implicit follow-up requests that exceed the one-request bound."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Reject redirects as HTTP errors without echoing response contents."""

        del req, fp, msg, headers, newurl
        raise ProviderHTTPError(code)


@dataclass(frozen=True)
class ChatCompletionReply(ModelReply):
    """Carry provider response metadata without expanding the shared ModelPort contract."""

    request_id: str = "unknown"
    finish_reason: str = "unknown"
    warnings: tuple[str, ...] = ()


def validate_api_key(value: str) -> None:
    if not value or not value.strip() or any(ch in value for ch in "\r\n"):
        raise ProviderConfigurationError("API_KEY must be a non-empty header-safe value")


def validate_base_url(url: str, host: str) -> bool:
    try:
        parsed = urlsplit(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname == host
            and parsed.port in (None, 443)
            and parsed.path.rstrip("/") in {"", "/v1"}
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
        )
    except ValueError:
        return False


def read_json(request: urllib.request.Request, *, timeout: float, max_bytes: int) -> dict[str, Any]:
    """Read one bounded JSON response and classify transport failures."""
    try:
        opener = urllib.request.build_opener(_RejectRedirects, *_proxy_handlers())
        with opener.open(request, timeout=timeout) as response:
            body = response.read(max_bytes + 1)
    except urllib.error.HTTPError as error:
        raise ProviderHTTPError(error.code) from None
    except TimeoutError:
        raise ProviderTimeoutError(
            "provider request timed out; remote outcome may be unknown"
        ) from None
    except urllib.error.URLError as error:
        if isinstance(error.reason, TimeoutError):
            raise ProviderTimeoutError(
                "provider request timed out; remote outcome may be unknown"
            ) from None
        raise ProviderOutcomeUnknownError(
            "provider transport failed; remote outcome is unknown"
        ) from None
    except (http.client.HTTPException, OSError):
        raise ProviderOutcomeUnknownError(
            "provider transport failed; remote outcome is unknown"
        ) from None

    if len(body) > max_bytes:
        raise ProviderProtocolError("provider response exceeded the configured size limit")

    return _decode_response(body)


def _proxy_handlers() -> tuple[urllib.request.ProxyHandler, ...]:
    """Use the environment's proxy settings and fall back to Windows settings."""

    proxies = urllib.request.getproxies()
    if not any(name in proxies for name in ("http", "https")):
        proxies = _windows_ie_proxies()
    return (urllib.request.ProxyHandler(proxies),)


def _windows_ie_proxies() -> dict[str, str]:
    """Read the enabled Windows system proxy without persisting its value."""

    if sys.platform != "win32" or os.environ.get("HTTPS_PROXY"):
        return {}
    try:
        import ctypes
        from ctypes import wintypes

        class ProxyConfig(ctypes.Structure):
            _fields_ = [
                ("auto_detect", wintypes.BOOL),
                ("auto_config_url", wintypes.LPWSTR),
                ("proxy", wintypes.LPWSTR),
                ("proxy_bypass", wintypes.LPWSTR),
            ]

        config = ProxyConfig()
        if not ctypes.windll.winhttp.WinHttpGetIEProxyConfigForCurrentUser(ctypes.byref(config)):
            return {}
        if not config.proxy:
            return {}
        proxy_url = config.proxy if "://" in config.proxy else f"http://{config.proxy}"
        bypass = os.environ.get("no_proxy") or config.proxy_bypass or ""
        return {"http": proxy_url, "https": proxy_url, "no": bypass}
    except (AttributeError, OSError, TypeError, ValueError):
        return {}


def post_chat_completion(
    url: str,
    *,
    api_key: str,
    payload: dict[str, Any],
    timeout: float,
    max_bytes: int,
    track1_usage: bool = False,
) -> ChatCompletionReply:
    """Submit one chat request without following redirects or retrying."""
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    response_data = read_json(request, timeout=timeout, max_bytes=max_bytes)
    choices = response_data.get("choices")
    choice = (
        choices[0]
        if isinstance(choices, list) and choices and isinstance(choices[0], dict)
        else None
    )
    message = choice.get("message") if choice is not None else None
    persisted_fields = (
        response_data.get("id"),
        response_data.get("model"),
        choice.get("finish_reason") if choice is not None else None,
        message.get("content") if isinstance(message, dict) else None,
    )
    if any(isinstance(value, str) and api_key in value for value in persisted_fields):
        raise ProviderProtocolError("provider response echoed its credential")

    usage = response_data.get("usage")
    if not isinstance(usage, dict):
        usage = {}
    warnings = ()
    if track1_usage:
        details = usage.get("completion_tokens_details")
        output = _token_count(usage.get("completion_tokens"))
        reasoning = _token_count(details.get("reasoning_tokens")) if isinstance(details, dict) else "unknown"
        if isinstance(output, int) and isinstance(reasoning, int) and output < reasoning <= output + 4:
            warnings = ("usage_subtotal_minor_drift",)
    metadata = ChatCompletionReply(
        text="",
        model=_nonempty_string(response_data.get("model")) or "unknown",
        input_tokens=_token_count(usage.get("prompt_tokens")),
        output_tokens=_token_count(usage.get("completion_tokens")),
        usage_source="provider" if _has_usage(usage) else "unknown",
        request_id=_nonempty_string(response_data.get("id")) or "unknown",
        finish_reason=_nonempty_string(choice.get("finish_reason")) or "unknown"
        if choice is not None
        else "unknown",
        warnings=warnings,
    )
    if choice is None:
        raise ProviderProtocolError(
            "provider response did not contain a chat choice", reply=metadata
        )
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise ProviderProtocolError(
            "provider response did not contain text content", reply=metadata
        )
    return replace(metadata, text=message["content"])


def _decode_response(body: bytes) -> dict[str, Any]:
    """Decode only a UTF-8 JSON object and keep provider bytes out of diagnostics."""

    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProviderProtocolError("provider response was not valid UTF-8 JSON") from None
    if not isinstance(value, dict):
        raise ProviderProtocolError("provider response was not a JSON object")
    return value


def _nonempty_string(value: object) -> str | None:
    """Accept an existing non-empty provider string without rendering other values."""

    return value if isinstance(value, str) and value else None


def _token_count(value: object) -> int | str:
    """Preserve recognized token-count values and mark absent data unknown."""

    return value if type(value) is int and value >= 0 else "unknown"


def _has_usage(usage: dict[str, Any]) -> bool:
    """Mark usage as provider-sourced only when at least one token count is present."""

    return any(
        _token_count(usage.get(key)) != "unknown" for key in ("prompt_tokens", "completion_tokens")
    )
