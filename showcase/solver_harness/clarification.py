"""Versioned necessary questions and conservative applicability after user input."""

from collections.abc import Mapping
from copy import deepcopy

from ..redaction import redact
from .specification import normalize_problem_spec
from .specification_change import build_specification_change


def waiting_for_clarification(state):
    return state.get("clarification", {}).get("status") == "waiting"


def necessary_question(run, intake, question, *, version=1):
    """Bind an intake question to this task and its current input version."""
    if not isinstance(question, Mapping) or any(
        not isinstance(question.get(key), str) or not question[key].strip() or len(question[key]) > 1000
        for key in ("question", "reason")
    ):
        raise ValueError("problem_intake_invalid_clarification")
    return {
        "clarification": {"request_id": f"clarification:{run['run_id']}:{version}",
                          "task_id": run["run_id"], "input_version": version,
                          "question": redact(question["question"]), "reason": redact(question["reason"]),
                          "status": "waiting"},
        "problem_intake": {**intake, "status": "pending"},
        "status": "waiting_input",
    }


def answer_change(state, condition, intake):
    """Make the user's answer an effective condition, invalidating prior conclusions."""
    question = state["clarification"]
    revised = deepcopy(state["problem_spec"])
    revised["specification_version"] += 1
    revised["assumptions"].append(f"用户对必要问题「{question['question']}」的补充条件：{condition}")
    revised = normalize_problem_spec(revised)
    change = build_specification_change(state, revised)
    change["event"]["clarification_request_id"] = question["request_id"]
    # A clarification changes the effective inputs of every prior candidate.
    candidates = deepcopy(state.get("candidate_registry"))
    from .candidates import latest_records

    for item in latest_records(candidates):
        if item["review_state"] == "invalidated":
            continue
        candidates.append({**deepcopy(item), "version": item["version"] + 1,
                           "review_state": "invalidated", "selection_eligible": False,
                           "invalidated_by": [*item.get("invalidated_by", []), change["event"]["event_id"]]})
    change["updates"].update({
        "clarification": {**question, "status": "answered"},
        "problem_intake": intake,
        "phase": "SETUP", "plan": {}, "exploration_findings": [],
        "candidate_registry": candidates, "best_effort_decision": None,
    })
    return change
