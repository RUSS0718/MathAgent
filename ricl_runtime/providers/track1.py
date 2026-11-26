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
SILICONFLOW_MODEL = "Qwen/Qwen3-14B"
SILICONFLOW_MODELS = {
    "Qwen/Qwen3-14B": (Decimal("0.07"), Decimal("0.28"), True),
    "Qwen/Qwen3-30B-A3B-Instruct-2507": (Decimal("0.09"), Decimal("0.30"), False),
    "Qwen/Qwen3.5-35B-A3B": (Decimal("0.24"), Decimal("1.80"), True),
    "deepseek-ai/DeepSeek-V3.2": (Decimal("0.28"), Decimal("0.42"), True),
    "deepseek-ai/DeepSeek-V4-Flash": (Decimal("0.15"), Decimal("0.60"), True),
    "deepseek-ai/DeepSeek-V4.1-Flash": (Decimal("0.15"), Decimal("0.60"), True),
    "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B": (Decimal("0.05"), Decimal("0.20"), False),
}
HOST_MODELS = {
    HOST: {MODEL: (INPUT_RATE, OUTPUT_RATE, True)},
    OFFICIAL_HOST: {"deepseek-flash": (Decimal("0.30"), Decimal("1.20"), True)},
    SILICONFLOW_HOST: SILICONFLOW_MODELS,
}
PROFILES = {
    HOST: (MODEL, INPUT_RATE, OUTPUT_RATE),
    OFFICIAL_HOST: ("deepseek-flash", Decimal("0.30"), Decimal("1.20")),
    SILICONFLOW_HOST: (SILICONFLOW_MODEL, Decimal("0.07"), Decimal("0.28")),
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
    supports_thinking: bool = True

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
        host = next((host for host in HOST_MODELS if validate_base_url(base_url, host)), None)
        if host is None:
            raise ProviderConfigurationError("BASE_URL must select a supported Track 1 provider")
        model = os.environ.get("MODEL", "")
        model_spec = HOST_MODELS[host].get(model)
        if model_spec is None:
            raise ProviderConfigurationError("MODEL must match the selected Track 1 provider")
        input_rate, output_rate, supports_thinking = model_spec
        key = os.environ.get("API_KEY", "")
        validate_api_key(key)
        if not 8192 <= max_output_tokens <= 32768:
            raise ProviderConfigurationError("Track 1 max_tokens must be between 8192 and 32768")
        timeout = 300.0 if host == SILICONFLOW_HOST else 180.0
        return cls(
            key,
            max_output_tokens,
            reasoning_effort,
            timeout=timeout,
            name=model,
            host=host,
            input_rate=input_rate,
            output_rate=output_rate,
            supports_thinking=supports_thinking,
        )

    def complete(
        self, prompt: str, *, json_mode: bool = False, max_output_tokens: int | None = None,
    ) -> ChatCompletionReply:
        """Submit only the public task context for this request."""
        effective_max = self.max_output_tokens if max_output_tokens is None else max_output_tokens
        if self.host == SILICONFLOW_HOST:
            payload: dict[str, object] = {
                "model": self.name,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": effective_max,
                "stream": True,
                "stream_options": {"include_usage": True},
            }
            if self.supports_thinking:
                enable_thinking = self.reasoning_effort != "none" and not json_mode
                payload["enable_thinking"] = enable_thinking
                if enable_thinking:
                    cap = 2048 if self.reasoning_effort == "low" else 4096
                    payload["thinking_budget"] = max(1024, min(cap, effective_max - 2048))
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
        max_bytes = 8_388_608 if self.host == SILICONFLOW_HOST else 1_048_576
        return post_chat_completion(
            f"https://{self.host}{path}",
            api_key=self.api_key,
            payload=payload,
            timeout=self.timeout,
            max_bytes=max_bytes,
            track1_usage=True,
        )
