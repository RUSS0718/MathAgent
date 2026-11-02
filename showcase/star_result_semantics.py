"""Read-only product meaning from the solver's audited whole-review binding.

This projection never upgrades legacy mathematical evidence or writes solver state.
"""

from .solver_harness.final_binding import review_binding


def result_semantics(run, answer, *, verification_mode="auto", execution_status=None):
    """Separate execution, transport, whole review, binding and formal evidence."""
    state = run["state"]
    review = review_binding(run, answer)
    bound = review == {"whole_review": "accepted", "binding": "same_artifact"}
    calls = list(state.get("calls", {}).values())
    # The existing product lifecycle wins over unfinished solver progress (e.g.
    # cancellation during an in-flight call). This is a projection, not a gate.
    execution = {
        "QUEUED": "queued", "RECEIVED": "queued", "RUNNING": "running",
        "WAITING_INPUT": "waiting_input", "COMPLETED": "completed",
        "NEEDS_REVIEW": "needs_review", "FAILED": "failed", "CANCELED": "canceled",
    }.get(execution_status)
    if execution is None:
        execution = ("completed" if state["status"] == "completed_llm_reviewed" and bound
                     and verification_mode != "required" else
                     "running" if state["status"] == "running" and state["phase"] != "TERMINAL"
                     else "needs_review")
    if execution == "completed" and (not bound or verification_mode == "required"):
        execution = "needs_review"
    unresolved = any(call.get("status") in {"dispatched", "streaming"} for call in calls)
    unknown = any(call.get("status") == "unknown_outcome" for call in calls)
    return {
        "version": "star-result-semantics-v1",
        "execution": execution,
        "transport": ("unknown" if unknown or unresolved and execution != "running" else
                      "pending" if unresolved else "known" if calls else "unavailable"),
        **review,
        "formal_verification": "not_verified",
        "verification_requirement": "required_unmet" if verification_mode == "required" else "default",
    }
