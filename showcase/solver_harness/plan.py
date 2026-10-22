"""Structural validation of caller-supplied plans; no mathematical judgment."""

from collections.abc import Mapping
from typing import Any


def validate_plan(plan: Any) -> None:
    """Raise ValueError before dispatch if a plan cannot be executed safely."""
    if not isinstance(plan, Mapping):
        raise ValueError("plan must be a mapping")
    version = plan.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError("plan.version must be a positive integer")
    steps = plan.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= 20:
        raise ValueError("plan.steps must contain 1..20 steps")
    seen = set()
    for step in steps:
        if not isinstance(step, Mapping):
            raise ValueError("plan step must be a mapping")
        step_id = step.get("step_id")
        if not isinstance(step_id, str) or not step_id.strip() or step_id in seen:
            raise ValueError("plan step IDs must be unique non-empty strings")
        objective = step.get("objective")
        if not isinstance(objective, str) or not objective.strip():
            raise ValueError("plan step objective must be a non-empty string")
        dependencies = step.get("depends_on", [])
        if not isinstance(dependencies, list) or any(
            not isinstance(dependency, str) or dependency not in seen for dependency in dependencies
        ):
            raise ValueError("plan dependencies must reference earlier steps")
        seen.add(step_id)
