"""Single-request DeepSeek chat-completion adapter for the Runtime ModelPort."""

import http.client
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

from ..port import ModelPortFailure, ModelReply

DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_RESPONSE_BYTES = 1_048_576
MAX_OUTPUT_TOKENS = 256
ALLOWED_HOST = "api.deepseek.com"
ALLOWED_MODELS = (
    "deepseek-flash",
    "deepseek-v4-flash",
    "deepseek-v4-flash-vision-exp",
)
MAX_PROMPT_BYTES = 16 * 1024
INPUT_FRAMING_MARGIN_TOKENS = 1024
COST_LIMIT_USD = Decimal("0.05")
INPUT_PEAK_USD_PER_MILLION = Decimal("0.30")
OUTPUT_PEAK_USD_PER_MILLION = Decimal("1.20")
PRICING_SOURCE = "https://api-docs.deepseek.com/quick_start/pricing/"
MAX_PREFLIGHT_INPUT_TOKENS = MAX_PROMPT_BYTES + INPUT_FRAMING_MARGIN_TOKENS
MAX_PREFLIGHT_COST_USD = (
    MAX_PREFLIGHT_INPUT_TOKENS * INPUT_PEAK_USD_PER_MILLION
    + MAX_OUTPUT_TOKENS * OUTPUT_PEAK_USD_PER_MILLION
) / Decimal(1_000_000)


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

    def __init__(self, message: str, *, reply: "DeepSeekReply | None" = None) -> None:
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
class DeepSeekReply(ModelReply):
    """Carry provider response metadata without expanding the shared ModelPort contract."""

    request_id: str = "unknown"
    finish_reason: str = "unknown"


@dataclass(frozen=True)
class DeepSeekModelPort:
    """Send one bounded, non-streaming chat completion through urllib."""

    api_key: str = field(repr=False)
    base_url: str
    model: str
    thinking: str = "disabled"

    def __post_init__(self) -> None:
        """Reject incomplete values without echoing credentials or URLs in errors."""

        if not self.api_key or not self.api_key.strip() or any(ch in self.api_key for ch in "\r\n"):
            raise ProviderConfigurationError("API_KEY must be a non-empty header-safe value")
        if not self.model or not self.model.strip():
            raise ProviderConfigurationError("MODEL must be non-empty")
        if self.thinking not in {"enabled", "disabled"}:
            raise ProviderConfigurationError("thinking must be enabled or disabled")

    @classmethod
    def from_environment(cls, *, thinking: str = "disabled") -> "DeepSeekModelPort":
        """Read only the three explicitly selected, non-persisted environment values."""

        api_key = os.environ.get("API_KEY")
        base_url = os.environ.get("BASE_URL")
        model = os.environ.get("MODEL")
        if not api_key or not base_url or not model:
            raise ProviderConfigurationError("API_KEY, BASE_URL, and MODEL must be configured")
        return cls(api_key=api_key, base_url=base_url, model=model, thinking=thinking)

    @property
    def name(self) -> str:
        """Expose the configured requested model through the existing ModelPort field."""

        return self.model

    @property
    def provider(self) -> str:
        """Identify this adapter without including endpoint or credential data."""

        return "deepseek"

    @property
    def max_output_tokens(self) -> int:
        """Expose the fixed completion-token ceiling for the Run config digest."""

        return MAX_OUTPUT_TOKENS

    @property
    def cost_limit_usd(self) -> float:
        """Expose the fixed per-request ceiling used by preflight."""

        return float(COST_LIMIT_USD)

    @property
    def preflight_cost_upper_bound_usd(self) -> str:
        """Expose the fixed worst-case input and output bound."""

        return format(MAX_PREFLIGHT_COST_USD, "f")

    @property
    def preflight_config(self) -> dict[str, object]:
        """Expose only non-secret request bounds and pricing inputs for the Run digest."""

        return {
            "endpoint_host": ALLOWED_HOST,
            "model_allowlist": list(ALLOWED_MODELS),
            "transport_timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
            "max_prompt_bytes": MAX_PROMPT_BYTES,
            "input_token_framing_margin": INPUT_FRAMING_MARGIN_TOKENS,
            "max_input_tokens_upper_bound": MAX_PREFLIGHT_INPUT_TOKENS,
            "peak_price_usd_per_million_tokens": {
                "input": str(INPUT_PEAK_USD_PER_MILLION),
                "output": str(OUTPUT_PEAK_USD_PER_MILLION),
            },
            "cost_limit_usd": self.cost_limit_usd,
            "preflight_cost_upper_bound_usd": self.preflight_cost_upper_bound_usd,
            "pricing_source": PRICING_SOURCE,
        }

    def complete(self, problem: str) -> DeepSeekReply:
        """Return one validated completion or a sanitized, non-retryable transport error."""

        try:
            parsed = urlsplit(self.base_url)
            valid_base_url = (
                parsed.scheme == "https"
                and parsed.hostname == ALLOWED_HOST
                and parsed.port in (None, 443)
                and parsed.path.rstrip("/") in {"", "/v1"}
                and parsed.username is None
                and parsed.password is None
                and not parsed.query
                and not parsed.fragment
            )
        except ValueError:
            valid_base_url = False
        if not valid_base_url or self.model not in ALLOWED_MODELS:
            raise ProviderPreflightError("provider host or model is not allowlisted")

        prompt_bytes = len(problem.encode("utf-8"))
        if prompt_bytes > MAX_PROMPT_BYTES:
            raise ProviderPreflightError("prompt exceeds the configured byte limit")
        input_tokens_upper_bound = prompt_bytes + INPUT_FRAMING_MARGIN_TOKENS
        cost_upper_bound = (
            input_tokens_upper_bound * INPUT_PEAK_USD_PER_MILLION
            + MAX_OUTPUT_TOKENS * OUTPUT_PEAK_USD_PER_MILLION
        ) / Decimal(1_000_000)
        if cost_upper_bound > COST_LIMIT_USD:
            raise ProviderPreflightError("request exceeds the configured cost limit")

        payload = json.dumps(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": problem}],
                "max_tokens": MAX_OUTPUT_TOKENS,
                "thinking": {"type": self.thinking},
            },
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
        choice = (
            choices[0]
            if isinstance(choices, list) and choices and isinstance(choices[0], dict)
            else None
        )

        usage = response_data.get("usage")
        if not isinstance(usage, dict):
            usage = {}
        metadata = DeepSeekReply(
            text="",
            model=_nonempty_string(response_data.get("model")) or "unknown",
            input_tokens=_token_count(usage.get("prompt_tokens")),
            output_tokens=_token_count(usage.get("completion_tokens")),
            usage_source="provider" if _has_usage(usage) else "unknown",
            request_id=_nonempty_string(response_data.get("id")) or "unknown",
            finish_reason=_nonempty_string(choice.get("finish_reason")) or "unknown"
            if choice is not None else "unknown",
        )
        if choice is None:
            raise ProviderProtocolError("provider response did not contain a chat choice", reply=metadata)
        message = choice.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise ProviderProtocolError("provider response did not contain text content", reply=metadata)
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
        _token_count(usage.get(key)) != "unknown"
        for key in ("prompt_tokens", "completion_tokens")
    )
