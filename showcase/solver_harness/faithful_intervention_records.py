"""Typed, validated records for faithful same-checkpoint interventions."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class FailureHypothesis:
    hypothesis_id: str
    failure_category: str
    evidence: Mapping[str, Any]
    candidate_action_ids: tuple[str, ...]
    falsification_criteria: Mapping[str, Any]


@dataclass(frozen=True)
class ProofAction:
    action_id: str
    action_type: str
    target: str
    parameters: Mapping[str, Any]


@dataclass(frozen=True)
class BranchOutcome:
    """A branch executor's observed result, never an engine-generated placeholder."""

    status: str
    measurement: float | int | None = None
    evidence: Mapping[str, Any] | None = None
    events: tuple[Mapping[str, Any], ...] = ()


class ParentJobGate(Protocol):
    """Verify the Job is durably paused at the requested Solver revision."""

    def assert_paused(
        self, *, connection: sqlite3.Connection, job_id: str,
        run_id: str, checkpoint_revision: int,
    ) -> None: ...


class FaithfulInterventionError(ValueError):
    """A requested intervention is invalid or conflicts with persisted identity."""


class BranchExecutor(Protocol):
    def __call__(self, *, checkpoint, action, branch_id, arm, budget, budget_role): ...


def _normalize_hypothesis(value: FailureHypothesis | Mapping[str, Any]) -> FailureHypothesis:
    if isinstance(value, Mapping):
        value = FailureHypothesis(**value)
    if not isinstance(value, FailureHypothesis):
        raise FaithfulInterventionError("failure_hypothesis_invalid")
    _required_text(value.hypothesis_id, "hypothesis_id")
    _required_text(value.failure_category, "failure_category")
    category_parts = value.failure_category.casefold().strip().replace("-", "_").split("_")
    if {"unknown", "transport", "connectivity", "connect", "network", "timeout",
        "provider", "http"} & set(category_parts):
        raise FaithfulInterventionError("hypothesis_category_noncausal")
    evidence = _json_mapping(value.evidence, "hypothesis_evidence_required")
    criteria = _json_mapping(value.falsification_criteria, "falsification_criteria_required")
    actions = value.candidate_action_ids
    if (not isinstance(actions, (tuple, list)) or len(actions) < 2
            or any(not isinstance(item, str) or not item.strip() for item in actions)):
        raise FaithfulInterventionError("candidate_actions_invalid")
    actions = tuple(item.strip() for item in actions)
    if len(set(actions)) != len(actions):
        raise FaithfulInterventionError("candidate_actions_invalid")
    return FailureHypothesis(
        value.hypothesis_id.strip(), value.failure_category.strip(), evidence,
        tuple(actions), criteria,
    )


def _normalize_action(value: ProofAction | Mapping[str, Any]) -> ProofAction:
    if isinstance(value, Mapping):
        value = ProofAction(**value)
    if not isinstance(value, ProofAction):
        raise FaithfulInterventionError("proof_action_invalid")
    _required_text(value.action_id, "action_id")
    _required_text(value.action_type, "action_type")
    _required_text(value.target, "action_target")
    parameters = _json_mapping(value.parameters, "action_parameters_required")
    return ProofAction(value.action_id.strip(), value.action_type.strip(), value.target.strip(), parameters)


def _required_text(value, reason):
    if not isinstance(value, str) or not value.strip():
        raise FaithfulInterventionError(reason)


def _single_parameter_difference(control: ProofAction, intervention: ProofAction) -> bool:
    if control.action_type != intervention.action_type or control.target != intervention.target:
        return False
    if control.parameters.keys() != intervention.parameters.keys():
        return False
    return sum(
        _encode(control.parameters[key]) != _encode(intervention.parameters[key])
        for key in control.parameters
    ) == 1


def _normalize_reservation(value):
    required = {"input_estimate", "output_cap"}
    optional = {"model_calls", "http_attempts", "tool_calls", "time_seconds"}
    if (not isinstance(value, Mapping) or not required.issubset(value)
            or set(value) - required - optional):
        raise FaithfulInterventionError("pair_reservation_invalid")
    if any(type(value[key]) is not int or value[key] < 0 for key in value):
        raise FaithfulInterventionError("pair_reservation_invalid")
    model_calls, attempts = value.get("model_calls", 1), value.get("http_attempts", 1)
    if model_calls < 1 or attempts < 1:
        raise FaithfulInterventionError("pair_reservation_invalid")
    return [{"role": "faithful_intervention", "http_attempts": attempts,
             "input_estimate": value["input_estimate"], "output_cap": value["output_cap"],
             **({"tool_calls": value.get("tool_calls", 0),
                 "time_seconds": value.get("time_seconds", 0)}
                if index == 0 and optional.intersection(value) else {})}
            for index in range(model_calls)]


def _json_mapping(value, reason):
    if not isinstance(value, Mapping) or not value:
        raise FaithfulInterventionError(reason)
    try:
        normalized = json.loads(_encode(dict(value)))
    except (TypeError, ValueError) as exc:
        raise FaithfulInterventionError("intervention_json_invalid") from exc
    return normalized


def _encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
