"""Deterministic APRS ranking for an already fixed candidate set."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Candidate:
    """A fixed search candidate and its evidence-independent estimates."""

    candidate_id: str
    novelty: int = 0
    known_token_cost: int | None = None
    verified_obligations_at_start: tuple[str, ...] = ()


@dataclass(frozen=True)
class VerifierEvidence:
    """Verifier feedback; tool receipts alone do not establish obligation gain."""

    candidate_id: str
    evidence_id: str
    obligation_id: str | None
    status: str
    valid: bool
    evidence_kind: str = "proof"


def evaluate_fixed_candidates(
    candidates: tuple[Candidate, ...],
    verifier_evidence: tuple[VerifierEvidence, ...],
    *,
    budget_snapshot: dict[str, Any],
    tool_capabilities: tuple[str, ...],
    verifier_capability: str,
    aprs_enabled: bool = True,
) -> dict[str, Any]:
    """Rank a fixed set from accepted verifier evidence without changing Run inputs."""

    candidate_ids = [candidate.candidate_id for candidate in candidates]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("candidate IDs must be unique")
    if any(item.candidate_id not in candidate_ids for item in verifier_evidence):
        raise ValueError("verifier evidence must reference a fixed candidate")

    evaluations = []
    for candidate in candidates:
        feedback = sorted(
            (item for item in verifier_evidence if item.candidate_id == candidate.candidate_id),
            key=lambda item: (item.evidence_id, item.obligation_id or "", item.status),
        )
        obligations_at_start = set(candidate.verified_obligations_at_start)
        obligations = sorted(
            {
                item.obligation_id
                for item in feedback
                if _counts_as_verified_gain(item, obligations_at_start)
            }
        )
        evidence_trace = [
            {
                "evidence_id": item.evidence_id,
                "obligation_id": item.obligation_id,
                "status": item.status,
                "valid": item.valid,
                "evidence_kind": item.evidence_kind,
                "counts_as_verified_gain": _counts_as_verified_gain(item, obligations_at_start),
            }
            for item in feedback
        ]
        evaluations.append(
            {
                "candidate_id": candidate.candidate_id,
                "candidate_snapshot": {
                    "novelty": candidate.novelty,
                    "known_token_cost": candidate.known_token_cost,
                    "verified_obligations_at_start": sorted(obligations_at_start),
                },
                "evidence_ids": [item.evidence_id for item in feedback],
                "verified_obligation_ids": obligations,
                "verifier_evidence": evidence_trace,
                "aprs_score": (
                    {
                        "verified_gain": len(obligations),
                        "evidence_quality": len(obligations),
                        "novelty": candidate.novelty,
                        "known_token_cost": candidate.known_token_cost,
                    }
                    if aprs_enabled
                    else None
                ),
            }
        )

    if aprs_enabled:
        priorities = _pareto_priority_order(evaluations)
    else:
        priorities = candidate_ids

    priority_by_id = {candidate_id: index + 1 for index, candidate_id in enumerate(priorities)}
    for evaluation in evaluations:
        evaluation["priority"] = priority_by_id[evaluation["candidate_id"]]

    ranking_mode = "aprs" if aprs_enabled else "plain_search"
    return {
        "ranking_enabled": aprs_enabled,
        "ranking_mode": ranking_mode,
        "candidate_ids": candidate_ids,
        "candidate_snapshots": [
            {"candidate_id": item["candidate_id"], **item["candidate_snapshot"]}
            for item in evaluations
        ],
        "priority_order": priorities,
        "budget_snapshot": deepcopy(budget_snapshot),
        "tool_capabilities": list(tool_capabilities),
        "verifier_capability": verifier_capability,
        "candidate_evaluations": evaluations,
        "trace": [
            {
                "event": "fixed_candidate_evaluated",
                "ranking_mode": ranking_mode,
                **evaluation,
            }
            for evaluation in evaluations
        ],
    }


def _counts_as_verified_gain(item: VerifierEvidence, obligations_at_start: set[str]) -> bool:
    """Count only new valid proof/goal obligations, never a tool receipt."""

    return (
        item.evidence_kind in {"proof", "goal"}
        and item.valid
        and item.status == "accepted"
        and item.obligation_id is not None
        and item.obligation_id not in obligations_at_start
    )


def _pareto_priority_order(evaluations: list[dict[str, Any]]) -> list[str]:
    """Rank the Pareto front first, then use a deterministic order for dominated options."""

    pareto = [
        candidate
        for candidate in evaluations
        if not any(_dominates(other, candidate) for other in evaluations if other is not candidate)
    ]
    dominated = [candidate for candidate in evaluations if candidate not in pareto]
    return [
        item["candidate_id"]
        for item in sorted(pareto, key=_tie_break_key) + sorted(dominated, key=_tie_break_key)
    ]


def _dominates(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Compare evidence, novelty and cost without collapsing them into one score."""

    left_score = left["aprs_score"]
    right_score = right["aprs_score"]
    maximized = ("verified_gain", "evidence_quality", "novelty")
    if any(left_score[key] < right_score[key] for key in maximized):
        return False
    left_cost = left_score["known_token_cost"]
    right_cost = right_score["known_token_cost"]
    if (left_cost is None) != (right_cost is None):
        return False
    if left_cost is not None and left_cost > right_cost:
        return False
    return any(left_score[key] > right_score[key] for key in maximized) or (
        left_cost is not None and left_cost < right_cost
    )


def _tie_break_key(evaluation: dict[str, Any]) -> tuple[Any, ...]:
    score = evaluation["aprs_score"]
    cost = score["known_token_cost"]
    return (
        -score["verified_gain"],
        -score["evidence_quality"],
        -score["novelty"],
        cost is None,
        cost if cost is not None else float("inf"),
        evaluation["candidate_id"],
    )
