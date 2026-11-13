"""Public task summaries from committed state; proof bodies remain in evidence."""

import re

from .redaction import redact_text


def public_text(value):
    """Suppress a sensitive summary in full: its value can span many words."""
    text = str(value)
    if (redact_text(text) != text or re.search(
            r"(?i)(authorization|credential|password|secret|token|api[_-]?key|"
            r"full[_-]?prompt|hidden[_-]?answer|personal[_-]?data|pii)\s*[:=]", text)):
        return "[redacted]"
    return text


def goal_summary(step):
    return " ".join(public_text(step.get("title", "")).split())[:200]


def current_proof_source(state, fact):
    """Ignore conjectures and retained classifications from earlier identities."""
    if fact.get("category") == "Conjecture" or fact.get("proven") is False:
        return False
    review = state.get("calls", {}).get(fact.get("review_call_id"), {})
    return all(key not in record or record[key] == state.get(key)
               for record in (fact, review)
               for key in ("plan_version", "attempt_index", "specification_version"))


def partial_progress(state, steps):
    from .solver_harness.aprs import _graph_source_current, verified_gain
    from .solver_harness.final_binding import review_binding
    from .solver_harness.finalize import valid_facts

    facts = [fact for fact in valid_facts(state)
             if (current_proof_source(state, fact) or fact in state.get("rescued_results", []))
             and _graph_source_current(state, fact)]
    current_steps = set()
    for step in (state.get("plan") or {}).get("steps", []):
        step_id = step["step_id"]
        review = state.get("steps", {}).get(step_id, {}).get("verification", {})
        sources = [fact for fact in state.get("verified_results_ledger", [])
                   if fact.get("source") == step_id and current_proof_source(state, fact)]
        if (review.get("valid") is True and review.get("verdict") == "ACCEPT"
                and all(dep in current_steps for dep in step.get("depends_on", []))
                and all(fact in facts for fact in sources)):
            current_steps.add(step_id)
    # Apply the same dependency closure to classified facts used by candidates.
    facts = [fact for fact in facts if fact.get("source") in current_steps
             or fact in state.get("rescued_results", [])]
    while any(dep not in current_steps and dep not in {f.get("result_id") for f in facts}
              for fact in facts for dep in fact.get("dependencies", [])):
        known = current_steps | {fact.get("result_id") for fact in facts}
        facts = [fact for fact in facts if all(dep in known for dep in fact.get("dependencies", []))]
    credit = verified_gain(state)
    required_satisfied = all(item.get("obligation_id") in credit
                             for item in state.get("obligation_ledger", []))
    candidates = []
    for attempt in state.get("final_solution_attempts", []):
        if (attempt.get("invalidated") or attempt.get("invalidated_by_specification_version")
                or attempt.get("specification_version") != state.get("specification_version")
                or attempt.get("plan_version") != state.get("plan_version")
                or attempt.get("attempt_index") != state.get("attempt_index")):
            continue
        verdict = (attempt.get("review") or {}).get("verdict", "UNREVIEWED")
        bound = review_binding({"run_id": state.get("run_id"), "state": state}, attempt["candidate"])
        eligible = (verdict == "ACCEPT"
                    and bound == {"whole_review": "accepted", "binding": "same_artifact"}
                    and all(fact in facts for fact in attempt.get("accepted_results", []))
                    and required_satisfied)
        candidates.append({"answer_text": public_text(attempt["candidate"]),
                           "review": verdict, "eligible": eligible})
    unresolved = [f"义务 {i}" for i, item in enumerate(state.get("obligation_ledger", []), 1)
                  if item.get("obligation_id") not in credit]
    if not candidates or not candidates[-1]["eligible"]:
        unresolved.append("whole_solution_review")
    return {"accepted_steps": [item["label"] for step, item in zip(
                (state.get("plan") or {}).get("steps", []), steps)
                if step["step_id"] in current_steps],
            "candidates": candidates, "unresolved": unresolved}
