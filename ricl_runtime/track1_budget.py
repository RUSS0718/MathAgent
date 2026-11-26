"""Reserve and record the shared token and cost budget for Track 1 calls."""

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal

from .port import ModelPortFailure
from .providers.chat_completions import ChatCompletionReply
from .providers.track1 import Track1Provider, estimated_cost


class RunStop(Exception):
    """Signal a bounded or failed stop using a sanitized classification."""

    def __init__(self, status: str, reason: str) -> None:
        self.status = status
        self.reason = reason


@dataclass
class SharedBudget:
    """Count all attempted stages under one Run-level request and token ceiling."""

    provider: Track1Provider
    token_limit: int
    request_limit: int
    cost_limit: Decimal
    emit: Callable[[dict], None]
    tokens: int = 0
    requests: int = 0
    cost: Decimal = Decimal(0)
    reserved_cost: Decimal = Decimal(0)
    usage_unknown: int = 0
    warnings: set[str] = field(default_factory=set)
    actions: list[str] = field(default_factory=list)

    def complete(self, stage: str, prompt: str, **context: object) -> ChatCompletionReply:
        """Reserve before dispatch and settle with provider totals or a preflight bound."""
        input_upper = len(prompt.encode("utf-8")) + 1024
        output_limit = self.provider.max_output_tokens
        cost_upper = estimated_cost(input_upper, output_limit)
        if self.requests >= self.request_limit:
            raise RunStop("stopped", "request_limit")
        if self.tokens + input_upper + output_limit > self.token_limit:
            raise RunStop("stopped", "token_limit")
        if self.reserved_cost + cost_upper > self.cost_limit:
            raise RunStop("stopped", "cost_limit")
        self.requests += 1
        self.reserved_cost += cost_upper
        if isinstance(action := context.get("action"), str):
            self.actions.append(action)
        self.emit({"event": "request_started", "call": self.requests, "stage": stage,
                   "input_upper": input_upper, "output_limit": output_limit,
                   "cost_upper_usd": str(cost_upper), **context})
        try:
            reply = self.provider.complete(prompt)
        except ModelPortFailure as exc:
            reply = getattr(exc, "reply", None)
            self._settle(reply, cost_upper)
            reason = exc.failure_status
            http_status = getattr(exc, "status_code", None)
            if http_status == 524:
                reason = "unknown_outcome"
            self.emit({"event": "request_failed", "call": self.requests,
                       "failure": reason, "http_status": http_status,
                       "request_sent": getattr(exc, "request_sent", "unknown"),
                       "input_tokens": getattr(reply, "input_tokens", "unknown"),
                       "output_tokens": getattr(reply, "output_tokens", "unknown")})
            raise RunStop("failed", reason) from None
        self._settle(reply, cost_upper)
        self.emit({"event": "request_finished", "call": self.requests,
                   "input_tokens": reply.input_tokens, "output_tokens": reply.output_tokens,
                   "reasoning_tokens": reply.reasoning_tokens,
                   "usage_source": reply.usage_source, "finish_reason": reply.finish_reason,
                   "content_present": bool(reply.text.strip()), "known_total_tokens": self.tokens,
                   "warnings": list(reply.warnings)})
        if self.usage_unknown:
            raise RunStop("failed", "unknown_usage")
        if self.tokens > self.token_limit or self.cost > self.cost_limit:
            raise RunStop("failed", "provider_usage_exceeded_run_budget")
        if reply.input_tokens > input_upper or reply.output_tokens > output_limit:
            raise RunStop("failed", "provider_usage_exceeded_request_reservation")
        if not reply.text.strip():
            raise RunStop("failed", "empty_content")
        return reply

    def _settle(self, reply: ChatCompletionReply | None, cost_upper: Decimal) -> None:
        """Keep known subtotal and reserve unknown monetary usage at the upper bound."""
        input_tokens = getattr(reply, "input_tokens", "unknown")
        output_tokens = getattr(reply, "output_tokens", "unknown")
        self.tokens += sum(value for value in (input_tokens, output_tokens) if type(value) is int)
        if type(input_tokens) is int and type(output_tokens) is int:
            self.cost += estimated_cost(input_tokens, output_tokens)
        else:
            self.usage_unknown += 1
            self.cost += cost_upper
        self.warnings.update(getattr(reply, "warnings", ()))
