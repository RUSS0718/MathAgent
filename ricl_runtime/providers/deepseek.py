"""Single-request DeepSeek chat-completion adapter for the Runtime ModelPort."""

import http.client
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from ..port import ModelReply

DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_RESPONSE_BYTES = 1_048_576


class ProviderConfigurationError(ValueError):
    """Report missing or malformed adapter configuration without exposing values."""


class ProviderHTTPError(RuntimeError):
    """Report a complete non-success HTTP response using only its status code."""

    def __init__(self, status_code: int) -> None:
        """Retain a safe status code without response headers or body."""

        self.status_code = status_code
        super().__init__(f"provider returned HTTP status {status_code}")


class ProviderProtocolError(RuntimeError):
    """Report an invalid or over-limit successful provider response, redacted."""


class ProviderTimeoutError(TimeoutError):
    """Report that the single provider request exceeded its transport timeout."""


class ProviderOutcomeUnknownError(ConnectionError):
    """Report an interrupted request whose remote completion cannot be known."""


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    """Prevent implicit follow-up requests that exceed the one-request bound."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Reject redirects as HTTP errors without echoing response contents."""

        del req, fp, msg, headers, newurl
        raise ProviderHTTPError(code)


@dataclass(frozen=True)
class DeepSeekReply(ModelReply):
    """Carry the provider request ID without expanding the shared ModelPort contract."""

    request_id: str = "unknown"


@dataclass(frozen=True)
class DeepSeekModelPort:
    """Send one bounded, non-streaming chat completion through urllib."""

    api_key: str = field(repr=False)
    base_url: str
    model: str

    def __post_init__(self) -> None:
        """Reject incomplete values without echoing credentials or URLs in errors."""

        if not self.api_key or not self.api_key.strip() or any(ch in self.api_key for ch in "\r\n"):
            raise ProviderConfigurationError("API_KEY must be a non-empty header-safe value")
        if not self.model or not self.model.strip():
            raise ProviderConfigurationError("MODEL must be non-empty")
        try:
            parsed = urlsplit(self.base_url)
            valid_base_url = (
                parsed.scheme in {"http", "https"}
                and bool(parsed.netloc)
                and parsed.username is None
                and parsed.password is None
                and not parsed.query
                and not parsed.fragment
            )
        except ValueError:
            valid_base_url = False
        if not valid_base_url:
            raise ProviderConfigurationError("BASE_URL must be an HTTP(S) base URL")

    @classmethod
    def from_environment(cls) -> "DeepSeekModelPort":
        """Read only the three explicitly selected, non-persisted environment values."""

        api_key = os.environ.get("API_KEY")
        base_url = os.environ.get("BASE_URL")
        model = os.environ.get("MODEL")
        if not api_key or not base_url or not model:
            raise ProviderConfigurationError("API_KEY, BASE_URL, and MODEL must be configured")
        return cls(api_key=api_key, base_url=base_url, model=model)

    @property
    def name(self) -> str:
        """Expose the configured requested model through the existing ModelPort field."""

        return self.model

    def complete(self, problem: str) -> DeepSeekReply:
        """Return one validated completion or a sanitized, non-retryable transport error."""

        payload = json.dumps(
            {"model": self.model, "messages": [{"role": "user", "content": problem}]},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            opener = urllib.request.build_opener(_RejectRedirects)
            with opener.open(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
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

        if len(body) > MAX_RESPONSE_BYTES:
            raise ProviderProtocolError("provider response exceeded the configured size limit")

        response_data = _decode_response(body)
        choices = response_data.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ProviderProtocolError("provider response did not contain a chat choice")
        message = choices[0].get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise ProviderProtocolError("provider response did not contain text content")

        usage = response_data.get("usage")
        if not isinstance(usage, dict):
            usage = {}
        return DeepSeekReply(
            text=message["content"],
            model=_nonempty_string(response_data.get("model")) or "unknown",
            input_tokens=_token_count(usage.get("prompt_tokens")),
            output_tokens=_token_count(usage.get("completion_tokens")),
            usage_source="provider" if _has_usage(usage) else "unknown",
            request_id=_nonempty_string(response_data.get("id")) or "unknown",
        )


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

    return value if isinstance(value, (int, str)) and not isinstance(value, bool) else "unknown"


def _has_usage(usage: dict[str, Any]) -> bool:
    """Mark usage as provider-sourced only when at least one token count is present."""

    return any(
        _token_count(usage.get(key)) != "unknown"
        for key in ("prompt_tokens", "completion_tokens")
    )
