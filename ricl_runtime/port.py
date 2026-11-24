"""Model-port contracts for the independent offline Runtime."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ModelReply:
    """A free-text model result with optional provider-reported metadata."""

    text: str
    model: str = "unknown"
    input_tokens: int | str = "unknown"
    output_tokens: int | str = "unknown"
    usage_source: str = "unknown"


class ModelPort(Protocol):
    """Small seam through which the Runtime requests one free-text answer."""

    name: str

    def complete(self, problem: str) -> ModelReply:
        """Return one answer without controlling Runtime state or budgets."""


@dataclass(frozen=True)
class DeterministicModelPort:
    """Offline test port that returns the caller-supplied answer unchanged."""

    answer: str
    name: str = "deterministic-offline"

    def complete(self, problem: str) -> ModelReply:
        """Return a fixed reply and make no network or provider request."""

        del problem
        return ModelReply(text=self.answer, model=self.name)
