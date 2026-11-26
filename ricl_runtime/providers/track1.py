"""Bounded Track 1 profiles for explicitly configured providers."""

import os
from dataclasses import dataclass, field
from decimal import Decimal

from .chat_completions import (
    ChatCompletionReply,
    ProviderConfigurationError,
    post_chat_completion,
    validate_api_key,
    validate_base_url,
)

HOST = "cn2.ezaigc.cn"
MODEL = "deepseek-v4.1-flash"
INPUT_RATE = Decimal("0.80")
OUTPUT_RATE = Decimal("3.20")
OUTPUT_LIMIT = 16384
OFFICIAL_HOST = "api.deepseek.com"
SILICONFLOW_HOST = "api.siliconflow.cn"
SILICONFLOW_MODEL = "Qwen/Qwen3.5-35B-A3B"
PROFILES = {
    HOST: (MODEL, INPUT_RATE, OUTPUT_RATE),
    OFFICIAL_HOST: ("deepseek-flash", Decimal("0.30"), Decimal("1.20")),
    SILICONFLOW_HOST: (SILICONFLOW_MODEL, Decimal("0.24"), Decimal("1.80")),
}


@dataclass(frozen=True)
class Track1Provider:
    """Send stateless single-message requests with no retries or endpoint fallback."""

    api_key: str = field(repr=False)
    max_output_tokens: int = OUTPUT_LIMIT
    reasoning_effort: str = "high"
    timeout: float = 180
    name: str = MODEL
    host: str = HOST
    input_rate: Decimal = INPUT_RATE
    output_rate: Decimal = OUTPUT_RATE

    def estimated_cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        """Use peak uncached rates as a conservative estimate."""
        return (input_tokens * self.input_rate + output_tokens * self.output_rate) / 1_000_000

    @property
    def thinking(self) -> str:
        """Keep the API thinking switch consistent with the configured effort."""
        return "disabled" if self.reasoning_effort == "none" else "enabled"

    @classmethod
    def from_environment(cls, max_output_tokens: int, reasoning_effort: str) -> "Track1Provider":
        """Require the local credential to have been selected for this gateway."""
        base_url = os.environ.get("BASE_URL", "")
        host = next((host for host in PROFILES if validate_base_url(base_url, host)), None)
        if host is None:
            raise ProviderConfigurationError("BASE_URL must select a supported Track 1 provider")
        model, input_rate, output_rate = PROFILES[host]
        if os.environ.get("MODEL") != model:
            raise ProviderConfigurationError("MODEL must match the selected Track 1 provider")
        key = os.environ.get("API_KEY", "")
        validate_api_key(key)
        if not 8192 <= max_output_tokens <= 32768:
            raise ProviderConfigurationError("Track 1 max_tokens must be between 8192 and 32768")
        return cls(key, max_output_tokens, reasoning_effort, name=model, host=host,
                   input_rate=input_rate, output_rate=output_rate)

    def complete(
        self, prompt: str, *, json_mode: bool = False, max_output_tokens: int | None = None,
    ) -> ChatCompletionReply:
        """Submit only the public task context for this request."""
        effective_max = self.max_output_tokens if max_output_tokens is None else max_output_tokens
        if self.host == SILICONFLOW_HOST:
            enable_thinking = self.reasoning_effort != "none" and not json_mode
            payload: dict[str, object] = {
                "model": self.name,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": effective_max,
                "enable_thinking": enable_thinking,
            }
            if enable_thinking:
                effort_frac = 0.25 if self.reasoning_effort == "low" else 0.5
                budget = max(1024, min(effective_max - 2048, int(effective_max * effort_frac)))
                payload["thinking_budget"] = budget
        else:
            payload = {
                "model": self.name,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": effective_max,
                "thinking": {"type": self.thinking},
                "reasoning_effort": self.reasoning_effort,
            }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        path = "/chat/completions" if self.host == OFFICIAL_HOST else "/v1/chat/completions"
        return post_chat_completion(
            f"https://{self.host}{path}",
            api_key=self.api_key,
            payload=payload,
            timeout=self.timeout,
            max_bytes=1_048_576,
            track1_usage=True,
        )
