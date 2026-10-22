"""Pure hard-budget candidate selection; no model or tool operation is reachable here.

Rule v1: evidence tier descending, then candidate_id in Unicode lexicographic order.
Different top-tier text hashes remain unresolved (possibly equivalent) alternatives.
"""

from copy import deepcopy

from .candidates import latest_records
from .finalize import budget_reason
from .harness_config import _hash_json

RULE_VERSION = "evidence-tier-then-candidate-id-v1"


def _independent(record, state):
    from .confidence import applicable_independent_refs

    return applicable_independent_refs(record, state)


def _rank(record, state):
    from .confidence import verified_whole_review_refs

    if record["review_state"] == "whole_reviewed" and verified_whole_review_refs(
        record, state, events=state.get("_events", [])
    ):
        return 3
    if _independent(record, state):
        return 2
    return 1 if record["review_state"] == "locally_reviewed" else 0


def _valid_dependencies(state, records):
    invalid = {
        result["result_id"]
        for failure in state.get("failure_records", [])
        for result in failure.get("invalidated_results", [])
        if result.get("result_id")
    }
    known = {
        step_id
        for step_id, step in state.get("steps", {}).items()
        if step.get("verification", {}).get("valid") is True
        and step["verification"].get("verdict") == "ACCEPT"
    }
    results = [
        r
        for r in state.get("accepted_results", [])
        if not r.get("invalidated")
        and r.get("valid", True)
        and r.get("result_id") not in invalid
        and r.get("source") in known
        and r.get("evidence_level") in {"llm_reviewed", "tool_verified"}
    ]
    pending = [*results, *records]
    changed = True
    while changed:
        changed = False
        for item in pending:
            key = item.get("candidate_id", item.get("result_id"))
            deps = item.get("dependency_refs", item.get("dependencies"))
            if (
                key
                and key not in known
                and key not in invalid
                and isinstance(deps, list)
                and all(d in known for d in deps)
            ):
                known.add(key)
                changed = True
    return known


def select_best_effort(snapshot):
    """Return a deterministic decision from a persisted ProblemState only."""
    records = latest_records(snapshot.get("candidate_registry"))
    exclusions, eligible = {}, []
    for record in records:
        cid = record["candidate_id"]
        reason = None
        if not isinstance(record.get("answer_text"), str) or not record["answer_text"].strip():
            reason = "blank_or_invalid_answer"
        elif record.get("answer_completeness") != "complete":
            reason = "incomplete_answer"
        elif record.get("review_state") in {"draft", "refuted", "invalidated"} or record.get(
            "invalidated_by"
        ):
            reason = "ineligible_review_state"
        elif record.get("selection_eligible") is not True:
            reason = "selection_disabled"
        if reason:
            exclusions[cid] = [reason]
        else:
            eligible.append(record)
    known = _valid_dependencies(snapshot, eligible)
    valid = []
    for record in eligible:
        if record["candidate_id"] not in known:
            exclusions[record["candidate_id"]] = ["invalid_or_missing_dependency"]
        else:
            valid.append(record)
    decision = {
        "status": "no_eligible_candidate",
        "selected_candidate_id": None,
        "confidence_level": None,
        "reason_codes": ["no_eligible_candidate"],
        "evidence_refs": [],
        "unresolved_issues": [],
        "excluded_candidate_ids": sorted(exclusions),
        "exclusion_reasons": exclusions,
        "selection_rule_version": RULE_VERSION,
        "termination_reason": snapshot.get("budget", {}).get(
            "exhaustion_reason", "hard_budget_exhausted"
        ),
        "selected_source_record": None,
    }
    if not valid:
        return decision
    ranked = sorted(valid, key=lambda record: (-_rank(record, snapshot), record["candidate_id"]))
    chosen = deepcopy(ranked[0])
    peers = [
        record
        for record in ranked[1:]
        if _rank(record, snapshot) == _rank(chosen, snapshot)
        and record["answer_text"] != chosen["answer_text"]
    ]
    if peers:
        chosen["conflicting_candidate_ids"] = [record["candidate_id"] for record in peers]
    from .confidence import grade_candidate

    grade = grade_candidate(chosen, snapshot, events=snapshot.get("_events", []))
    decision.update(
        status="candidate_selected",
        selected_candidate_id=chosen["candidate_id"],
        selected_source_record=chosen,
        confidence_level=grade["confidence_level"],
        reason_codes=["evidence_ranked", *grade["reason_codes"]],
        evidence_refs=grade["evidence_refs"],
        unresolved_issues=grade["unresolved_questions"],
    )
    if peers:
        decision["reason_codes"] = list(
            dict.fromkeys([*decision["reason_codes"], "candidate_conflict"])
        )
        decision["unresolved_issues"].append("semantic_equivalence_unverified")
    return decision


def run_best_effort(harness, run, *, require_termination=False):
    """Only the computed hard-budget transition may update an already terminal run."""
    config = harness._config
    state = run["state"]
    if (
        config.get("features", {}).get("best_effort") is not True
        or state.get("best_effort_decision") is not None
    ):
        return run
    if require_termination and state["status"] != "partial_budget_exhausted":
        return run
    reason = budget_reason(state, config)
    if not reason and state["status"] != "partial_budget_exhausted":
        return run
    if state["status"] == "completed_llm_reviewed":
        return run
    snapshot = deepcopy(state)
    snapshot["_events"] = deepcopy(run["events"])
    snapshot["budget"] = {
        **state.get("budget", {}),
        "exhaustion_reason": reason
        or state["budget"].get("exhaustion_reason", "hard_budget_exhausted"),
    }
    decision = select_best_effort(snapshot)
    selected = decision["selected_source_record"]
    updates = {
        "phase": "TERMINAL",
        "status": "partial_budget_exhausted",
        "best_effort_decision": decision,
        "finalization_reason": decision["termination_reason"],
        "budget": snapshot["budget"],
        "final_response": selected["answer_text"]
        if selected
        else "未能在预算内求得合格的完整答案。",
    }
    event = {
        "event_id": f"best-effort-{run['state_revision']}",
        "type": "best_effort_selected" if selected else "best_effort_empty",
        "candidate_id": decision["selected_candidate_id"],
        "evidence_refs": decision["evidence_refs"],
        "usage_source": "no_additional_calls",
    }
    # This narrow internal transition accepts no caller-provided patch and preserves
    # the generic terminal freeze in commit_event. CAS protects concurrent recovery.
    return harness._state_store.commit_event(
        run["run_id"],
        expected_revision=run["state_revision"],
        event=event,
        state_updates=updates,
        request_hash=_hash_json({"event": event, "state_updates": updates}),
    )
