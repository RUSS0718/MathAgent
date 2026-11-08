"""Atomic lifecycle and APRS derivations for serial-route state commits."""

from __future__ import annotations


def terminal_route_patch(run_id, state):
    if state.get("route_policy", {}).get("enabled") is not True:
        return {}
    route_id = state.get("active_route_id")
    route = next((item for item in state.get("route_registry", [])
                  if item.get("route_id") == route_id), None)
    if route is None or route.get("status") in {"completed", "terminated", "pruned"}:
        return {"active_route_id": None} if route_id is not None else {}
    status = state.get("status")
    answer = state.get("final_response")
    verified = False
    if status == "completed_llm_reviewed" and isinstance(answer, str):
        from .final_binding import delivery_verification

        verified, _ = delivery_verification({"run_id": run_id, "state": state}, answer)
    target = "completed" if verified else "terminated"
    reason = "final_answer_bound" if verified else _terminal_reason(status)
    from .routes import transition_route

    return {**transition_route(state, route_id, target, reason=reason), "active_route_id": None}


def rating_required(previous, current):
    if current.get("route_policy", {}).get("enabled") is not True:
        return False
    if not current.get("route_registry"):
        return False
    if previous.get("route_registry") != current.get("route_registry"):
        return True
    if ((previous.get("proof_graph") or {}).get("current_version")
            != (current.get("proof_graph") or {}).get("current_version")):
        return True
    if ((previous.get("progress") or {}).get("trigger")
            != (current.get("progress") or {}).get("trigger")):
        return True
    if ((previous.get("progress") or {}).get("no_evidence_rounds")
            != (current.get("progress") or {}).get("no_evidence_rounds")):
        return True
    from .aprs import verified_gain

    if verified_gain(previous) != verified_gain(current):
        return True
    return (
        previous.get("phase") != current.get("phase")
        and current.get("phase") in {"FINAL_GENERATE", "FINAL_REVIEW", "TERMINAL"}
    )


def rating_patch(state, revision):
    from .aprs import rate_routes, replay_decision

    preview = {**state, "state_revision": revision}
    evaluations, decision = rate_routes(preview)
    if not replay_decision(evaluations, decision):
        raise ValueError("route_decision_replay_failed")
    return {
        "route_evaluations": [
            *state.get("route_evaluations", []),
            {"state_revision": revision, "evaluations": evaluations},
        ],
        "aprs_decisions": [
            *state.get("aprs_decisions", []),
            {"state_revision": revision, **decision},
        ],
    }


def _terminal_reason(status):
    return {
        "partial_aborted": "run_aborted",
        "partial_budget_exhausted": "budget_exhausted",
        "completed_unverified": "run_completed_unverified",
        "failed": "run_failed",
        "canceled": "run_canceled",
        "interrupted": "run_interrupted",
    }.get(status, "run_terminal_unverified")
