"""Scoped ProblemSpec revision and dependency-based evidence invalidation."""

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

_GLOBAL_REQUIREMENTS = (
    "original_problem", "domain", "quantifiers", "assumptions", "directions",
    "output_requirements",
)


def _objective_maps(specification):
    roots = {item["obligation_id"]: item for item in specification["root_obligations"]}
    goals = {item["goal_id"]: item for item in specification["auxiliary_goals"]}
    return roots, goals


def _affected_objectives(old, new):
    old_roots, old_goals = _objective_maps(old)
    new_roots, new_goals = _objective_maps(new)
    roots_changed = {
        key for key in set(old_roots) | set(new_roots)
        if old_roots.get(key) != new_roots.get(key)
    }
    goals_changed = {
        key for key in set(old_goals) | set(new_goals)
        if old_goals.get(key) != new_goals.get(key)
    }
    if any(old.get(key) != new.get(key) for key in _GLOBAL_REQUIREMENTS):
        roots_changed.update(set(old_roots) | set(new_roots))
        goals_changed.update(set(old_goals) | set(new_goals))
    changed = roots_changed | goals_changed
    while True:
        before = set(changed)
        for objective in [*old_roots.values(), *new_roots.values()]:
            if set(objective.get("prerequisite_ids", [])) & changed:
                changed.add(objective["obligation_id"])
        for objective in [*old_goals.values(), *new_goals.values()]:
            if set(objective.get("dependencies", [])) & changed:
                changed.add(objective["goal_id"])
        if changed == before:
            break
    return changed & (set(old_roots) | set(new_roots)), changed & (set(old_goals) | set(new_goals))


def build_specification_change(state: Mapping[str, Any], revised: Mapping[str, Any]):
    """Return a same-transaction event and state patch for one accepted revision."""
    old = state["problem_spec"]
    affected_roots, affected_goals = _affected_objectives(old, revised)
    plan = state.get("plan") or {}
    plan_steps = plan.get("steps", [])
    units = state.get("work_units", [])
    affected_steps = {
        item.get("step_id", item.get("work_unit_id")) for item in units
        if set(item.get("obligation_ids", [])) & affected_roots
        or set(item.get("auxiliary_goal_ids", [])) & affected_goals
    }
    changed = True
    while changed:
        before = set(affected_steps)
        for step in plan_steps:
            if set(step.get("depends_on", [])) & affected_steps:
                affected_steps.add(step["step_id"])
        for item in units:
            step_id = item.get("step_id", item.get("work_unit_id"))
            if step_id in affected_steps:
                affected_roots.update(item.get("obligation_ids", []))
                affected_goals.update(item.get("auxiliary_goal_ids", []))
        changed = before != affected_steps

    invalid_nodes = set(affected_steps) | affected_roots | affected_goals
    records = [*state.get("accepted_results", []), *state.get("verified_results_ledger", [])]
    invalidated_results = []
    invalid_result_ids = set()
    changed = True
    while changed:
        before = set(invalid_nodes)
        for result in records:
            if (result.get("source") in invalid_nodes
                    or set(result.get("dependencies", [])) & invalid_nodes):
                result_id = result.get("result_id")
                if result_id:
                    invalid_nodes.add(result_id)
                    invalid_result_ids.add(result_id)
        changed = before != invalid_nodes

    def should_invalidate_result(result):
        return (
            result.get("source") in invalid_nodes
            or result.get("result_id") in invalid_result_ids
            or bool(set(result.get("dependencies", [])) & invalid_nodes)
        )

    for result in records:
        if should_invalidate_result(result):
            invalidated_results.append({
                **deepcopy(result),
                "invalidated": True,
                "invalidated_by_specification_version": revised["specification_version"],
            })

    evidence = []
    for record in state.get("obligation_evidence_ledger", []):
        item = deepcopy(record)
        if (item.get("obligation_id") in affected_roots
                or item.get("source") in affected_steps):
            item["invalidated"] = True
            item["invalidated_by_specification_version"] = revised["specification_version"]
        elif item.get("invalidated") is not True:
            item["applicable_specification_versions"] = list(dict.fromkeys(
                item.get("applicable_specification_versions", [old["specification_version"]])
                + [revised["specification_version"]]
            ))
        evidence.append(item)

    accepted_results, verified_results = [], []
    for source, target in ((state.get("accepted_results", []), accepted_results),
                           (state.get("verified_results_ledger", []), verified_results)):
        for item in source:
            copied = deepcopy(item)
            if should_invalidate_result(copied):
                copied["invalidated"] = True
                copied["invalidated_by_specification_version"] = revised["specification_version"]
            target.append(copied)

    steps = deepcopy(state.get("steps", {}))
    for step_id in affected_steps:
        if step_id in steps:
            steps[step_id] = {
                **steps[step_id],
                "status": "INVALIDATED",
                "invalidated_by_specification_version": revised["specification_version"],
            }
    failure = {
        "kind": "problem_spec_change",
        "from_specification_version": old["specification_version"],
        "to_specification_version": revised["specification_version"],
        "affected_obligation_ids": sorted(affected_roots),
        "affected_auxiliary_goal_ids": sorted(affected_goals),
        "archived_steps": {
            key: deepcopy(value) for key, value in state.get("steps", {}).items()
            if key in affected_steps
        },
        "archived_plan": deepcopy(plan),
        "invalidated_results": invalidated_results,
        "rescued_results": [],
    }
    from .obligation_evidence import update_obligation_ledger

    ledger = update_obligation_ledger(revised, state.get("obligation_ledger", []), evidence)
    final_solution_attempts = []
    for attempt in state.get("final_solution_attempts", []):
        copied = deepcopy(attempt)
        if copied.get("specification_version") != revised["specification_version"]:
            copied.update(
                invalidated=True,
                invalidated_by_specification_version=revised["specification_version"],
            )
        final_solution_attempts.append(copied)
    whole_solution_reviews = []
    for review in state.get("whole_solution_reviews", []):
        copied = deepcopy(review)
        source = copied.get("source", {})
        if source.get("specification_version") != revised["specification_version"]:
            copied.update(
                invalidated=True,
                invalidated_by_specification_version=revised["specification_version"],
            )
        whole_solution_reviews.append(copied)
    invalidation = {
        "from_specification_version": old["specification_version"],
        "to_specification_version": revised["specification_version"],
        "affected_obligation_ids": sorted(affected_roots),
        "affected_work_unit_ids": sorted(item for item in affected_steps if item),
        "unaffected_obligation_ids": sorted(
            {item["obligation_id"] for item in revised["root_obligations"]} - affected_roots
        ),
    }
    return {
        "event": {
            "event_id": f"problem-spec-revised-{revised['specification_version']}",
            "type": "problem_spec_revised",
            "from_specification_version": old["specification_version"],
            "to_specification_version": revised["specification_version"],
            "affected_obligation_count": len(affected_roots),
            "root_coverage_after_revision": sum(item["status"] == "satisfied" for item in ledger),
            "root_obligation_count": len(ledger),
        },
        "updates": {
            "problem_spec": revised,
            "specification_version": revised["specification_version"],
            "specification_history": [*state.get("specification_history", [old]), revised],
            "obligation_ledger": ledger,
            "obligation_evidence_ledger": evidence,
            "final_solution_attempts": final_solution_attempts,
            "whole_solution_reviews": whole_solution_reviews,
            "accepted_results": accepted_results,
            "verified_results_ledger": verified_results,
            "steps": steps,
            "phase": "PLAN",
            "current_step": None,
            "status": "running",
            "final_response": "",
            "work_units": [],
            "meta_decision": None,
            "meta_guidance_decision": None,
            "pending_guidance_task": None,
            "failure_records": [*state.get("failure_records", []), failure],
            "specification_invalidations": [
                *state.get("specification_invalidations", []), invalidation
            ],
        },
    }
