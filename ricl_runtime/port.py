"""Model and controlled-tool contracts for the independent offline Runtime."""

from dataclasses import dataclass
from typing import Protocol


class ModelPortFailure(Exception):
    """A sanitized model-call failure with a stable Run classification."""

    failure_status = "unknown_outcome"


@dataclass(frozen=True)
class ToolCall:
    """A model-proposed call, which is not evidence until an executor returns a receipt."""

    tool_name: str
    input: str


@dataclass(frozen=True)
class ModelReply:
    """A free-text model result with optional provider metadata and tool proposals."""

    text: str
    model: str = "unknown"
    input_tokens: int | str = "unknown"
    output_tokens: int | str = "unknown"
    usage_source: str = "unknown"
    tool_calls: tuple[ToolCall, ...] = ()
    action: str | None = None
    route: str | None = None


@dataclass(frozen=True)
class ToolReceipt:
    """A controlled executor's correlated result for a proposed tool invocation."""

    invocation_id: str
    receipt_id: str
    tool_name: str
    success: bool
    output: str


class ModelPort(Protocol):
    """Small seam through which the Runtime sends one bounded free-text request."""

    name: str

    def complete(self, problem: str) -> ModelReply:
        """Return one answer without controlling Runtime state or budgets."""


class ToolExecutor(Protocol):
    """Controlled capability that may return evidence-bearing execution receipts."""

    def execute(self, invocation_id: str, call: ToolCall) -> ToolReceipt:
        """Execute a proposed call and return its correlated result."""


@dataclass(frozen=True)
class DeterministicModelPort:
    """Offline port that returns the caller-supplied answer without network access."""

    answer: str
    name: str = "deterministic-offline"

    def complete(self, problem: str) -> ModelReply:
        """Return a fixed reply unchanged and make no Provider request."""

        del problem
        return ModelReply(text=self.answer, model=self.name)