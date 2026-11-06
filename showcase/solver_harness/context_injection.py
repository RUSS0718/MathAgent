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
    if request.get("acceptance_mode") == "handoff":
        context["acceptance_mode"] = "handoff"
        context["reviewed_drafts"] = deepcopy(request.get("reviewed_drafts", []))
    if request.get("finalization_scope") is True:
        # Final synthesis and review receive the already dependency-checked facts
        # plus the proof bodies of still-valid accepted steps with their real
        # computation receipts; dead derivations live only in failure records.
        context.pop("confirmed_failures_ledger", None)
        context["accepted_results"] = deepcopy(request.get("accepted_results", []))
        context["step_proofs"] = deepcopy(request.get("step_proofs", []))
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
        keys = ("plan", "steps", "accepted_results", "verified_results_ledger",
                "failure_records", "meta_interventions", "replan_count")
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
    if role in {"reasoner", "reason_noncoding"}:
        from .traceback import transition_decision

        decision = state.get("meta_decision")
        if transition_decision(run, state, decision) and decision.get("decision") == "CONTINUE":
            # Strategy context only; it neither rewrites the goal nor proves it.
            context["meta_decision"] = deepcopy(decision)
    if role in {"meta", "meta_strategist"}:
        from .computation_evidence import has_computation_output

        relevant_steps = {state.get("current_step")} | {
            step_id for step_id, step in state.get("steps", {}).items()
            if step.get("verification", {}).get("valid") is True
            and step["verification"].get("verdict") == "ACCEPT"
        }
        # Verifier computations need not be copied into the Reasoner's report.
        # Supply their actual output without duplicating code or failed attempts.
        fields = ("receipt_id", "step_id", "plan_version", "attempt_index", "tool",
                  "status", "executed", "exit_code", "input_ref", "output", "stdout_ref", "source")
        context["tool_receipts"] = [
            {key: deepcopy(receipt[key]) for key in fields if key in receipt}
            for receipt in state.get("tool_receipts", [])
            if receipt.get("run_id") == run["run_id"]
            and receipt.get("plan_version") == state["plan_version"]
            and receipt.get("attempt_index") == state["attempt_index"]
            and receipt.get("step_id") in relevant_steps
            and receipt.get("executed") is True and receipt.get("status") == "success"
            and receipt.get("exit_code") == 0 and receipt.get("unknown_outcome") is not True
            and has_computation_output(receipt)
        ]
    return {
        "run_id": run["run_id"],
        "state_revision": run["state_revision"],
        "role": role,
        "state": context,
    }
