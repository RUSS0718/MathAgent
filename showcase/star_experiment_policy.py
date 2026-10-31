"""Trusted experiment Run ceilings. S3 still owns every action reservation."""

import time

from .run_budget import RunBudgetLimits


class ExperimentRunPolicy:
    def __init__(self, deadline_at, *, phase_deadline_at=None):
        self.round_deadline_at = deadline_at
        self.phase_deadline_at = phase_deadline_at
        self.run_deadline_at = None
        self.limits = RunBudgetLimits(max_model_calls=0, max_http_attempts=0,
                                     max_tool_calls=0, max_tokens=0, max_runtime_seconds=0)

    def prepare(self, limits):
        self.limits = RunBudgetLimits(**limits)
        self.run_deadline_at = time.time() + self.limits.max_runtime_seconds

    @property
    def deadline_at(self):
        return min(self.round_deadline_at, self.run_deadline_at) if self.run_deadline_at is not None else self.round_deadline_at

    def remaining(self):
        return max(0, self.deadline_at - time.time())

    def budget(self):
        return self.limits  # S3 clamps the original registered limits to deadline_at atomically.
