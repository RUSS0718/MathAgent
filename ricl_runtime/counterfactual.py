"""Public contracts for bounded, offline Runtime counterfactual branches."""

from dataclasses import dataclass, field
from typing import Literal

from .reasoning_state import SharedReasoningState


@dataclass
class CounterfactualCheckpoint:
    """A visible, bounded parent checkpoint shared by both isolated branches."""

    visible_prefix: str
    failure_count: int
    trigger_count: int = 0
    current_action: str | None = None
    current_route: str | None = None
    reasoning_state: SharedReasoningState = field(default_factory=SharedReasoningState)
    max_trigger_count: int = 1

    def __post_init__(self) -> None:
        if not self.visible_prefix.strip():
            raise ValueError("counterfactual checkpoints require a visible prefix")
        counts = (self.failure_count, self.trigger_count, self.max_trigger_count)
        if any(type(count) is not int for count in counts):
            raise TypeError("counterfactual trigger counts must be integers")
        if self.failure_count < 0 or self.trigger_count < 0 or self.max_trigger_count < 1:
            raise ValueError("counterfactual trigger counts must be nonnegative and bounded")
        if self.trigger_count > self.max_trigger_count:
            raise ValueError("counterfactual trigger count exceeds its maximum")
        if not isinstance(self.reasoning_state, SharedReasoningState):
            raise TypeError("counterfactual checkpoint requires a shared reasoning state")


@dataclass(frozen=True)
class InterventionAudit:
    """Independent audit outcome required before treatment feedback reaches its parent."""

    status: Literal["approved", "rejected", "unknown"]
    source: str
    feedback_consumed: bool

    def __post_init__(self) -> None:
        if self.status not in ("approved", "rejected", "unknown"):
            raise ValueError("unsupported intervention audit status")
        if not self.source.strip():
            raise ValueError("intervention audits require a source")
        if type(self.feedback_consumed) is not bool:
            raise TypeError("feedback consumption must be an explicit boolean")
