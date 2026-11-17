"""One audited semantic ruling for a rejected, required graph premise."""

from copy import deepcopy

from .classified import graph_step_result


def scope_id(state, step_id):
    return (f"{state['run_id']}:dependency-review:{state['plan_version']}:"
            f"{state['attempt_index']}:{step_id}")


def required(state, step_id):
    return (state.get("proof_graph_policy", {}).get("enabled") is True
            and any(step_id in step.get("depends_on", [])
                    for step in state.get("plan", {}).get("steps", [])))


def saved_review(state, step_id):
    """Only consume the same report/spec/checkpoint; never renew the scope quota."""
    saved = state.get("dependency_reclassifications", {}).get(scope_id(state, step_id))
    step = state["steps"][step_id]
    if (saved and saved["specification_version"] == state.get("specification_version", 0)
            and saved["report"] == step.get("report")
            and saved["checkpoint_id"] == step.get("checkpoint_id")
            and (saved.get("checkpoint") is None
                 or saved["checkpoint"] in state.get("reasoner_checkpoints", []))):
        return saved
    return None


def consumable(state, step_id, outcomes, verification):
    """Use the unchanged source and graph validators, including conflict/closure."""
    if graph_step_result(state, step_id) is not None:
        return True
    if not outcomes or not verification["valid"]:
        return False
    from .proof_graph import evolve_proof_graph

    candidate = {**state, "steps": {**state["steps"], step_id: {
        **state["steps"][step_id], "verification": verification}},
        "verified_results_ledger": [*state.get("verified_results_ledger", []), *outcomes]}
    graph, _ = evolve_proof_graph(candidate, {"type": "step_reviewed"})
    if graph is not None:
        candidate["proof_graph"] = graph
    return graph_step_result(candidate, step_id) is not None


def completed_accept(state, call_id, step_id, report, verification):
    from .proof_graph_sources import recorded_call

    call = recorded_call(state, call_id, "step_verifier")
    return (verification["valid"] and verification["verdict"] == "ACCEPT"
            and call is not None and call.get("status") == "completed"
            and call.get("plan_version") == state["plan_version"]
            and call.get("attempt_index") == state["attempt_index"]
            and call.get("request", {}).get("problem_spec_version", 0)
            == state.get("specification_version", 0)
            and call.get("request", {}).get("step", {}).get("step_id") == step_id
            and (state["steps"][step_id].get("checkpoint_id") is None
                 or (call.get("request", {}).get("checkpoint") in state.get("reasoner_checkpoints", [])
                     and call["request"]["checkpoint"].get("checkpoint_id")
                     == state["steps"][step_id]["checkpoint_id"]))
            and call.get("request", {}).get("report") == report)


def reserve(harness, run, *, step_id, call_id, rejections):
    """Persist quota and original refusals before any new reservation/dispatch."""
    state = run["state"]
    identity = scope_id(state, step_id)
    record = {"call_id": identity, "original_call_id": call_id,
              "rejections": deepcopy(rejections),
              "specification_version": state.get("specification_version", 0),
              "report": deepcopy(state["steps"][step_id]["report"]),
              "checkpoint": deepcopy(state["calls"][call_id].get("request", {}).get("checkpoint")),
              "checkpoint_id": state["steps"][step_id].get("checkpoint_id")}
    return harness.commit_event(
        run["run_id"], expected_revision=run["state_revision"],
        event={"event_id": identity + ":reserved", "type": "dependency_review_reserved",
               "step_id": step_id, "original_call_id": call_id,
               "rejections": rejections},
        state_updates={"dependency_reclassifications": {
            **state.get("dependency_reclassifications", {}), identity: record}})


def request(state, step_id, problem):
    saved = saved_review(state, step_id)
    original = state["calls"][saved["original_call_id"]]["request"]
    # Keep the exact reviewed object; add only authoritative receipts and errors.
    return {**{key: deepcopy(original[key]) for key in (
                "run_id", "role", "session_key", "round", "step", "step_goal",
                "checkpoint", "report", "current_step_index") if key in original},
            "problem": problem, "call_id": saved["call_id"],
            "reclassification_of": saved["original_call_id"],
            "specification_version": saved["specification_version"],
            "admission_rejections": saved["rejections"],
            "authoritative_tool_receipts": deepcopy(state.get("tool_receipts", [])),
            "admission_instruction": (
                "The previous classification was refused for the attached admission errors. "
                "Re-evaluate this same report independently. Empty output is not computation "
                "evidence. Do not invent outputs or silently remove receipt references to "
                "preserve an old ACCEPT. You may establish an llm_reviewed result only from "
                "a sufficient independent mathematical argument, or decline it. Return the "
                "complete verifier ruling and classifications; no new computations are available.")}


def fail(harness, run, step_id):
    return harness.commit_event(
        run["run_id"], expected_revision=run["state_revision"],
        event={"event_id": f"dependency-review-failed-{run['state_revision']}",
               "type": "dependency_review_failed", "step_id": step_id,
               "reason": "dependency_reclassification_failed", "valid": False},
        state_updates={"phase": "TERMINAL", "status": "partial_aborted",
                       "result_reason": "dependency_reclassification_failed",
                       "final_response": "A required graph premise remains unsupported; review is needed."})
