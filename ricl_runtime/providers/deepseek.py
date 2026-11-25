"""Single-request DeepSeek chat-completion adapter for the Runtime ModelPort."""

import os
from dataclasses import dataclass, field
from decimal import Decimal

from .chat_completions import (
    ChatCompletionReply as DeepSeekReply,
)
from .chat_completions import (
    ProviderConfigurationError as ProviderConfigurationError,
)
from .chat_completions import (
    ProviderHTTPError as ProviderHTTPError,
)
from .chat_completions import (
    ProviderOutcomeUnknownError as ProviderOutcomeUnknownError,
)
from .chat_completions import (
    ProviderPreflightError as ProviderPreflightError,
)
from .chat_completions import (
    ProviderProtocolError as ProviderProtocolError,
)
from .chat_completions import (
    ProviderTimeoutError as ProviderTimeoutError,
)
from .chat_completions import (
    _RejectRedirects as _RejectRedirects,
)
from .chat_completions import (
    post_chat_completion,
    validate_api_key,
    validate_base_url,
)

DEFAULT_TIMEOUT_SECONDS = 60.0
MAX_RESPONSE_BYTES = 1_048_576
MAX_OUTPUT_TOKENS = 256
GATEWAY_MAX_OUTPUT_TOKENS = 16384
ALLOWED_HOST = "api.deepseek.com"
ALLOWED_GATEWAY_HOST = "code.aigcpro.org"
ALLOWED_MODELS = (
    "deepseek-flash",
    "deepseek-v4-flash",
    "deepseek-v4-flash-vision-exp",
)
GATEWAY_ALLOWED_MODELS = ("deepseek-v4.1-flash",)
MAX_PROMPT_BYTES = 16 * 1024
INPUT_FRAMING_MARGIN_TOKENS = 1024
COST_LIMIT_USD = Decimal("0.05")
GATEWAY_COST_LIMIT_USD = Decimal("0.07")
INPUT_PEAK_USD_PER_MILLION = Decimal("0.30")
OUTPUT_PEAK_USD_PER_MILLION = Decimal("1.20")
GATEWAY_INPUT_PEAK_USD_PER_MILLION = Decimal("0.80")
GATEWAY_OUTPUT_PEAK_USD_PER_MILLION = Decimal("3.20")
PRICING_SOURCE = "https://api-docs.deepseek.com/quick_start/pricing/"
GATEWAY_PRICING_SOURCE = "https://code.aigcpro.org/api/pricing"
GATEWAY_PRICING_UNIT_SOURCE = "https://code.aigcpro.org/api/status"
MAX_PREFLIGHT_INPUT_TOKENS = MAX_PROMPT_BYTES + INPUT_FRAMING_MARGIN_TOKENS
MAX_PREFLIGHT_COST_USD = (
    MAX_PREFLIGHT_INPUT_TOKENS * INPUT_PEAK_USD_PER_MILLION
    + MAX_OUTPUT_TOKENS * OUTPUT_PEAK_USD_PER_MILLION
) / Decimal(1_000_000)
GATEWAY_MAX_PREFLIGHT_COST_USD = (
    MAX_PREFLIGHT_INPUT_TOKENS * GATEWAY_INPUT_PEAK_USD_PER_MILLION
    + GATEWAY_MAX_OUTPUT_TOKENS * GATEWAY_OUTPUT_PEAK_USD_PER_MILLION
) / Decimal(1_000_000)


@dataclass(frozen=True)
class DeepSeekModelPort:
    """Send one bounded, non-streaming chat completion through urllib."""

    api_key: str = field(repr=False)
    base_url: str
    model: str
    thinking: str = "disabled"

    def __post_init__(self) -> None:
        """Reject incomplete values without echoing credentials or URLs in errors."""

        validate_api_key(self.api_key)
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

        return GATEWAY_MAX_OUTPUT_TOKENS if self._is_gateway else MAX_OUTPUT_TOKENS

    @property
    def _is_gateway(self) -> bool:
        return validate_base_url(self.base_url, ALLOWED_GATEWAY_HOST)

    @property
    def max_prompt_bytes(self) -> int:
        return MAX_PROMPT_BYTES

    @property
    def transport_timeout_seconds(self) -> float:
        return DEFAULT_TIMEOUT_SECONDS

    @property
    def _input_peak_usd_per_million(self) -> Decimal:
        return (
            GATEWAY_INPUT_PEAK_USD_PER_MILLION
            if self._is_gateway
            else INPUT_PEAK_USD_PER_MILLION
        )

    @property
    def _output_peak_usd_per_million(self) -> Decimal:
        return (
            GATEWAY_OUTPUT_PEAK_USD_PER_MILLION
            if self._is_gateway
            else OUTPUT_PEAK_USD_PER_MILLION
        )

    @property
    def cost_limit_usd(self) -> float:
        """Expose the fixed per-request ceiling used by preflight."""

        return float(GATEWAY_COST_LIMIT_USD if self._is_gateway else COST_LIMIT_USD)

    @property
    def preflight_cost_upper_bound_usd(self) -> str:
        """Expose the fixed worst-case input and output bound."""

        return format(
            GATEWAY_MAX_PREFLIGHT_COST_USD if self._is_gateway else MAX_PREFLIGHT_COST_USD,
            "f",
        )

    @property
    def preflight_config(self) -> dict[str, object]:
        """Expose only non-secret request bounds and pricing inputs for the Run digest."""

        return {
            "endpoint_host": ALLOWED_HOST,
            "gateway_host": ALLOWED_GATEWAY_HOST,
            "selected_endpoint_host": (
                ALLOWED_GATEWAY_HOST if self._is_gateway else ALLOWED_HOST
            ),
            "model_allowlist": list(
                GATEWAY_ALLOWED_MODELS if self._is_gateway else ALLOWED_MODELS
            ),
            "transport_timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
            "max_prompt_bytes": MAX_PROMPT_BYTES,
            "input_token_framing_margin": INPUT_FRAMING_MARGIN_TOKENS,
            "max_input_tokens_upper_bound": MAX_PREFLIGHT_INPUT_TOKENS,
            "peak_price_usd_per_million_tokens": {
                "input": str(self._input_peak_usd_per_million),
                "output": str(self._output_peak_usd_per_million),
            },
            "max_output_tokens": self.max_output_tokens,
            "cost_limit_usd": self.cost_limit_usd,
            "preflight_cost_upper_bound_usd": self.preflight_cost_upper_bound_usd,
            "pricing_source": PRICING_SOURCE,
            "gateway_pricing_source": GATEWAY_PRICING_SOURCE,
            "gateway_pricing_unit_source": GATEWAY_PRICING_UNIT_SOURCE,
        }

    def complete(self, problem: str) -> DeepSeekReply:
        """Return one validated completion or a sanitized, non-retryable transport error."""

        is_gateway = self._is_gateway
        approved_host = (
            is_gateway or validate_base_url(self.base_url, ALLOWED_HOST)
        )
        allowed_models = GATEWAY_ALLOWED_MODELS if is_gateway else ALLOWED_MODELS
        if not approved_host or self.model not in allowed_models:
            raise ProviderPreflightError("provider host or model is not allowlisted")

        prompt_bytes = len(problem.encode("utf-8"))
        if prompt_bytes > MAX_PROMPT_BYTES:
            raise ProviderPreflightError("prompt exceeds the configured byte limit")
        input_tokens_upper_bound = prompt_bytes + INPUT_FRAMING_MARGIN_TOKENS
        max_output_tokens = self.max_output_tokens
        cost_upper_bound = (
            input_tokens_upper_bound * self._input_peak_usd_per_million
            + max_output_tokens * self._output_peak_usd_per_million
        ) / Decimal(1_000_000)
        if cost_upper_bound > (GATEWAY_COST_LIMIT_USD if is_gateway else COST_LIMIT_USD):
            raise ProviderPreflightError("request exceeds the configured cost limit")

        return post_chat_completion(
            f"{self.base_url.rstrip('/')}/chat/completions",
            api_key=self.api_key,
            payload={
                "model": self.model,
                "messages": [{"role": "user", "content": problem}],
                "max_tokens": max_output_tokens,
                "thinking": {"type": self.thinking},
            },
            timeout=DEFAULT_TIMEOUT_SECONDS,
            max_bytes=MAX_RESPONSE_BYTES,
        )
