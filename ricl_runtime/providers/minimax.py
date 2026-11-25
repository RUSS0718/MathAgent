"""Single-request MiniMax adapter for the configured OpenAI-compatible gateway."""

import os
import re
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.request import Request

from ..port import ModelPortFailure
from .chat_completions import (
    ChatCompletionReply,
    ProviderConfigurationError,
    ProviderPreflightError,
    ProviderProtocolError,
    post_chat_completion,
    read_json,
    validate_api_key,
    validate_base_url,
)

GATEWAY_HOST = "cn2.ezaigc.cn"
GATEWAY_ROOT = f"https://{GATEWAY_HOST}"
MODEL_ID = "minimax-m3.1-flash"
PRICING_URL = f"{GATEWAY_ROOT}/api/pricing"
STATUS_URL = f"{GATEWAY_ROOT}/api/status"
MAX_OUTPUT_TOKENS = 256
MAX_PROMPT_BYTES = 16 * 1024
INPUT_FRAMING_MARGIN_TOKENS = 1024
MAX_RESPONSE_BYTES = 1_048_576
TIMEOUT_SECONDS = 30
COST_LIMIT_USD = Decimal("0.05")
_INLINE_REASONING = re.compile(r"<think\s*>.*?</think\s*>", re.IGNORECASE | re.DOTALL)
_REASONING_TAG = re.compile(r"</?think\b", re.IGNORECASE)


@dataclass(frozen=True)
class GatewayRates:
    """Use the highest published group multiplier for the selected model."""

    input_per_token: Decimal
    output_per_token: Decimal
    group_ratio: Decimal

    def cost_upper_bound(self, prompt_bytes: int) -> Decimal:
        return (
            prompt_bytes + INPUT_FRAMING_MARGIN_TOKENS
        ) * self.input_per_token + MAX_OUTPUT_TOKENS * self.output_per_token


def _ratio(value: object) -> Decimal:
    ratio = Decimal(str(value))
    if not ratio.is_finite() or ratio <= 0:
        raise ValueError("invalid gateway rate")
    return ratio


def _parse_gateway_rates(pricing: dict[str, Any], status: dict[str, Any]) -> GatewayRates:
    if pricing.get("success") is not True or status.get("success") is not True:
        raise ValueError("gateway metadata request failed")
    matches = [entry for entry in pricing["data"] if entry["model_name"] == MODEL_ID]
    if len(matches) != 1:
        raise ValueError("unique model rate unavailable")
    model = matches[0]
    if (
        model["quota_type"] != 0
        or model.get("billing_mode") not in (None, "", "token")
        or "openai" not in model["supported_endpoint_types"]
    ):
        raise ValueError("model has no compatible metered rate")
    groups = model["enable_groups"]
    if not isinstance(groups, list) or not groups:
        raise ValueError("model has no published groups")
    group = max(_ratio(pricing["group_ratio"][name]) for name in groups)
    units = _ratio(status["data"]["quota_per_unit"])
    input_price = _ratio(model["model_ratio"]) * group / units
    return GatewayRates(input_price, input_price * _ratio(model["completion_ratio"]), group)


def _public_gateway_rates() -> GatewayRates:
    try:
        pricing = read_json(Request(PRICING_URL), timeout=5, max_bytes=MAX_RESPONSE_BYTES)
        status = read_json(Request(STATUS_URL), timeout=5, max_bytes=MAX_RESPONSE_BYTES)
        return _parse_gateway_rates(pricing, status)
    except (ModelPortFailure, InvalidOperation, KeyError, TypeError, ValueError):
        raise ProviderPreflightError(
            "gateway pricing could not establish a request cost bound"
        ) from None


@dataclass
class MiniMaxModelPort:
    """Bind the approved gateway and model to the Runtime's existing ModelPort."""

    api_key: str = field(repr=False)
    base_url: str
    model: str
    _rates: GatewayRates | None = field(default=None, init=False, repr=False)
    _cost_bound: Decimal | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        validate_api_key(self.api_key)
        if not self.model.strip():
            raise ProviderConfigurationError("MINIMAX_MODEL must be non-empty")

    @classmethod
    def from_environment(cls) -> "MiniMaxModelPort":
        api_key, base_url, model = (
            os.environ.get(name) for name in ("API_KEY", "BASE_URL", "MINIMAX_MODEL")
        )
        if not api_key or not base_url or not model:
            raise ProviderConfigurationError(
                "API_KEY, BASE_URL, and MINIMAX_MODEL must be configured"
            )
        return cls(api_key, base_url, model)

    @property
    def name(self) -> str:
        return self.model

    @property
    def provider(self) -> str:
        return "ezaigc"

    @property
    def thinking(self) -> str:
        return "enabled"

    @property
    def max_output_tokens(self) -> int:
        return MAX_OUTPUT_TOKENS

    @property
    def preflight_config(self) -> dict[str, object]:
        rates = self._rates
        return {
            "endpoint_host": GATEWAY_HOST,
            "model_family": "minimax",
            "thinking": {"type": "enabled", "effort": "low"},
            "transport_timeout_seconds": TIMEOUT_SECONDS,
            "max_prompt_bytes": MAX_PROMPT_BYTES,
            "input_token_framing_margin": INPUT_FRAMING_MARGIN_TOKENS,
            "cost_limit_usd": float(COST_LIMIT_USD),
            "preflight_cost_upper_bound_usd": (
                format(self._cost_bound, "f") if self._cost_bound is not None else "unknown"
            ),
            "pricing_source": PRICING_URL,
            "pricing_unit_source": STATUS_URL,
            "maximum_published_group_ratio": str(rates.group_ratio) if rates else "unknown",
            "peak_price_usd_per_million_tokens": {
                "input": str(rates.input_per_token * 1_000_000) if rates else "unknown",
                "output": str(rates.output_per_token * 1_000_000) if rates else "unknown",
            },
        }

    def complete(self, problem: str) -> ChatCompletionReply:
        if not validate_base_url(self.base_url, GATEWAY_HOST) or self.model != MODEL_ID:
            raise ProviderPreflightError(
                "MiniMax gateway host or model is outside the validated configuration"
            )
        prompt_bytes = len(problem.encode("utf-8"))
        if prompt_bytes > MAX_PROMPT_BYTES:
            raise ProviderPreflightError("prompt exceeds the configured byte limit")

        self._rates = _public_gateway_rates()
        self._cost_bound = self._rates.cost_upper_bound(prompt_bytes)
        if self._cost_bound > COST_LIMIT_USD:
            raise ProviderPreflightError("request exceeds the configured cost limit")
        reply = post_chat_completion(
            f"{GATEWAY_ROOT}/v1/chat/completions",
            api_key=self.api_key,
            payload={
                "model": self.model,
                "messages": [{"role": "user", "content": problem}],
                "reasoning_effort": "low",
                "max_tokens": MAX_OUTPUT_TOKENS,
            },
            timeout=TIMEOUT_SECONDS,
            max_bytes=MAX_RESPONSE_BYTES,
        )
        metadata = replace(reply, text="")
        if isinstance(reply.output_tokens, int) and reply.output_tokens > MAX_OUTPUT_TOKENS:
            raise ProviderProtocolError(
                "gateway reported output beyond the requested cap", reply=metadata
            )
        text = _INLINE_REASONING.sub("", reply.text).strip()
        if _REASONING_TAG.search(text):
            if reply.finish_reason == "length":
                return metadata
            raise ProviderProtocolError("gateway returned unseparated reasoning", reply=metadata)
        if problem:
            text = text.replace(problem, "").strip()
        return replace(reply, text=text)
