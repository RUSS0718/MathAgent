"""Detached current-state projections for role dispatch."""

from copy import deepcopy


def prepare_role_context(run, request):
    state = run["state"]
    role = request["role"]
    keys = (
        "phase",
        "plan_version",
        "attempt_index",
        "current_step",
        "budget",
        "counters",
        "confirmed_failures_ledger",
    )
    context = {key: deepcopy(state[key]) for key in keys if key in state}
    if role in {"meta", "meta_strategist"}:
        keys = ("steps", "failure_records", "meta_interventions", "replan_count")
    else:
        keys = (
            "plan",
            "accepted_results",
            "verified_results_ledger",
            "failure_records",
            "rescued_results",
        )
    for key in keys:
        value = deepcopy(state.get(key, []))
        if key in {"accepted_results", "verified_results_ledger", "rescued_results"}:
            value = [
                item
                for item in value
                if not isinstance(item, dict)
                or (
                    item.get("valid", True)
                    and item.get("status") not in {"INVALIDATED", "invalidated"}
                    and not item.get("invalidated", False)
                )
            ]
        context[key] = value
    return {
        "run_id": run["run_id"],
        "state_revision": run["state_revision"],
        "role": role,
        "state": context,
    }
