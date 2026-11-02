"""Detached current-state projections for role dispatch."""

from copy import deepcopy


def prepare_role_context(run, request, *, include_exploration=False):
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
    if request.get("finalization_scope") is True:
        # Final synthesis and review receive the already dependency-checked facts only.
        context.pop("confirmed_failures_ledger", None)
        context["accepted_results"] = deepcopy(request.get("accepted_results", []))
        return {
            "run_id": run["run_id"],
            "state_revision": run["state_revision"],
            "role": role,
            "state": context,
        }
    invalid_ids = {
        result["result_id"]
        for failure in state.get("failure_records", [])
        for result in failure.get("invalidated_results", [])
        if isinstance(result, dict) and "result_id" in result
    }
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
        if include_exploration:
            keys = (*keys, "exploration_findings")
    for key in keys:
        value = deepcopy(state.get(key, []))
        if key == "exploration_findings":
            value = [{**item, "provenance": "unverified_exploration"}
                     for item in value if isinstance(item, dict)]
        if key in {"accepted_results", "verified_results_ledger", "rescued_results"}:
            value = [
                item
                for item in value
                if not isinstance(item, dict)
                or (
                    item.get("valid", True)
                    and item.get("status") not in {"INVALIDATED", "invalidated"}
                    and not item.get("invalidated", False)
                    and item.get("result_id") not in invalid_ids
                )
            ]
        context[key] = value
    return {
        "run_id": run["run_id"],
        "state_revision": run["state_revision"],
        "role": role,
        "state": context,
    }
