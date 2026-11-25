"""Contracts for bounded serial candidate-route expansion."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .aprs import Candidate


@dataclass(frozen=True)
class CandidateRoute:
    """One supplied route opportunity and its expansion reservation."""

    candidate: Candidate
    prompt: str
    source: str
    parent_route_id: str | None = None
    tool_calls_reserved: int = 0
    elapsed_ms_reserved: int | None = None
    cost_usd_reserved: float | None = None

    def __post_init__(self) -> None:
        if not self.candidate.candidate_id or not self.prompt or not self.source:
            raise ValueError("candidate route requires an ID, prompt, and source")
        if self.candidate.known_token_cost is not None and self.candidate.known_token_cost < 0:
            raise ValueError("token reservation must be nonnegative")
        if self.tool_calls_reserved < 0:
            raise ValueError("tool reservation must be nonnegative")
        if self.elapsed_ms_reserved is not None and self.elapsed_ms_reserved < 0:
            raise ValueError("elapsed-time reservation must be nonnegative")
        if self.cost_usd_reserved is not None and (
            not math.isfinite(self.cost_usd_reserved) or self.cost_usd_reserved < 0
        ):
            raise ValueError("cost reservation must be finite and nonnegative")


@dataclass(frozen=True)
class PopulationBudget:
    """One Run-wide hard admission budget for serial route opportunities."""

    model_requests: int
    tokens: int
    tools: int
    elapsed_ms: int
    cost_usd: float

    def __post_init__(self) -> None:
        if self.model_requests < 1:
            raise ValueError("model request budget must be positive")
        if min(self.tokens, self.tools, self.elapsed_ms) < 0:
            raise ValueError("population budgets must be nonnegative")
        if not math.isfinite(self.cost_usd) or self.cost_usd < 0:
            raise ValueError("cost budget must be finite and nonnegative")
