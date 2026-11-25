"""Contracts and independent evidence checks for counterfactual branches."""

import re
from dataclasses import dataclass, field
from random import Random
from typing import Literal

from .reasoning_state import SharedReasoningState
from .verification import evidence_reference


@dataclass(frozen=True)
class RepairOptions:
    """Common repair opportunities and the recorded diagnostic selection for a pair."""

    options: tuple[tuple[str, str], ...]
    diagnosed_id: str
    seed: int

    def __post_init__(self) -> None:
        ids = {option_id for option_id, _ in self.options}
        if len(ids) < 2 or len(ids) != len(self.options) or self.diagnosed_id not in ids:
            raise ValueError("repair options need distinct IDs and a diagnosis in the same pool")
        if any(
            not option_id.strip() or not feedback.strip() for option_id, feedback in self.options
        ):
            raise ValueError("repair options require a nonempty ID and feedback")

    def select(self, kind: Literal["random", "diagnostic"]) -> tuple[str, str]:
        """Choose blindly for random repair or use the diagnosed ID."""
        if kind == "random":
            return Random(self.seed).choice(self.options)
        return self.diagnosed_id, dict(self.options)[self.diagnosed_id]


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


@dataclass(frozen=True)
class AdditionRepairEvidence:
    """Distinguish repair routes by checking a public arithmetic witness."""

    left: int
    right: int

    @property
    def instructions(self) -> str:
        return (
            "Report one public Repair step line and a separate Final answer line. "
            "A direct step has the form Repair step: a + b = result. "
            "A regrouping step has the form Repair step: a + b = x + y + b = result, "
            "where x and y are both nonzero and sum to a. "
            "Use the original addends in their original order. Apply the suggested method if given. "
            "If citing verified evidence, give its ID on a separate Evidence used: line. "
            "Keep the response to these public, checkable fields."
        )

    def route(self, answer: str) -> str | None:
        lines = _labeled_lines(answer, "Repair step:")
        if len(lines) != 1:
            return None
        pieces = [part.strip() for part in lines[0].removesuffix(".").split("=")]
        if len(pieces) not in (2, 3):
            return None
        original = _integers_in_sum(pieces[0])
        result = _integers_in_sum(pieces[-1])
        if original != [self.left, self.right] or result != [self.left + self.right]:
            return None
        if len(pieces) == 2:
            return "direct"
        regrouping = _integers_in_sum(pieces[1])
        if regrouping is not None and len(regrouping) == 3:
            first, second, right = regrouping
            if first and second and first + second == self.left and right == self.right:
                return "regroup"
        return None

    def audit(
        self, selected_repair: str | None, control: str | None, treatment: str | None
    ) -> InterventionAudit:
        expected_route = {"recalculate": "direct", "regroup": "regroup"}.get(selected_repair)
        if expected_route is None or control is None or treatment is None:
            return InterventionAudit("unknown", "independent_arithmetic_witness", False)
        matched = treatment == expected_route
        return InterventionAudit(
            "approved" if matched and control != treatment else "rejected",
            "independent_arithmetic_witness",
            matched,
        )

    def parent_reference(self, answer: str, evidence_id: str, result_id: str) -> bool:
        lines = _labeled_lines(answer, "Evidence used:")
        if len(lines) != 1:
            return False
        citation = evidence_reference("Evidence used: " + lines[0])
        return citation in {(evidence_id, None), (evidence_id, result_id)}


def _labeled_lines(text: str, prefix: str) -> list[str]:
    return [
        line[len(prefix) :].strip()
        for raw in text.splitlines()
        if (line := raw.strip()).startswith(prefix)
    ]


def _integers_in_sum(text: str) -> list[int] | None:
    pieces = [piece.strip() for piece in text.split("+")]
    if all(re.fullmatch(r"-?[0-9]{1,18}", piece) for piece in pieces):
        return [int(piece) for piece in pieces]
    return None
