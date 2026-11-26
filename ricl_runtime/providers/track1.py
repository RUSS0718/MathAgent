"""Bounded Track 1 profile for the configured OpenAI-compatible gateway."""

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


def estimated_cost(input_tokens: int, output_tokens: int) -> Decimal:
    """Charge all input at the highest advertised group rate, ignoring cache discounts."""
    return (input_tokens * INPUT_RATE + output_tokens * OUTPUT_RATE) / 1_000_000


@dataclass(frozen=True)
class Track1Provider:
    """Send stateless single-message requests with no retries or endpoint fallback."""

    api_key: str = field(repr=False)
    max_output_tokens: int = OUTPUT_LIMIT
    reasoning_effort: str = "high"
    timeout: float = 180
    name: str = MODEL

    @property
    def thinking(self) -> str:
        """Keep the API thinking switch consistent with the configured effort."""
        return "disabled" if self.reasoning_effort == "none" else "enabled"

    @classmethod
    def from_environment(cls, max_output_tokens: int, reasoning_effort: str) -> "Track1Provider":
        """Require the local credential to have been selected for this gateway."""
        if not validate_base_url(os.environ.get("BASE_URL", ""), HOST):
            raise ProviderConfigurationError("BASE_URL must select the Track 1 gateway")
        if os.environ.get("MODEL") != MODEL:
            raise ProviderConfigurationError("MODEL must select the Track 1 model")
        key = os.environ.get("API_KEY", "")
        validate_api_key(key)
        if not 8192 <= max_output_tokens <= 32768:
            raise ProviderConfigurationError("Track 1 max_tokens must be between 8192 and 32768")
        return cls(key, max_output_tokens, reasoning_effort)

    def complete(self, prompt: str) -> ChatCompletionReply:
        """Submit only the public task context for this request."""
        return post_chat_completion(
            f"https://{HOST}/v1/chat/completions",
            api_key=self.api_key,
            payload={
                "model": self.name,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": self.max_output_tokens,
                "thinking": {"type": self.thinking},
                "reasoning_effort": self.reasoning_effort,
            },
            timeout=self.timeout,
            max_bytes=1_048_576,
            track1_usage=True,
        )
