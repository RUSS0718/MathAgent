"""Whitelist persisted mathematical progress without model text or internal IDs."""

from .final_evidence import artifact_identity
from .redaction import redact_text


def progress_summary(state):
    plan = state.get("plan") or {}
    steps = []
    for number, step in enumerate(plan.get("steps", []), 1):
        stored = state.get("steps", {}).get(step["step_id"], {})
        review = stored.get("verification", {})
        steps.append({"label": f"步骤 {number}",
            "current": state.get("current_step") == step["step_id"],
            "reported": bool(stored.get("report")),
            **{key: review[key] for key in ("verdict", "valid", "goal_gate", "logic_gate")
               if key in review}})
    summary = {"plan_version": state.get("plan_version"),
        "attempt_index": state.get("attempt_index"), "steps": steps,
        "failures": [{key: item[key] for key in ("kind", "plan_version", "attempt_index")
                      if key in item} | {
            "invalidated_count": len(item.get("invalidated_results", [])),
            "rescued_count": len(item.get("rescued_results", []))}
            for item in state.get("failure_records", [])],
        "classified_results": [
            {"category": item["category"],
             "scope": redact_text(str(item.get("scope", "")))[:200],
             "proven": item.get("proven") is True,
             "invalidated": bool(item.get("invalidated"))
             or item.get("status") in {"INVALIDATED", "invalidated"},
             "statement_digest": artifact_identity(str(item.get("statement", "")))["sha256"]}
            for item in state.get("verified_results_ledger", [])
            if isinstance(item, dict) and isinstance(item.get("category"), str)],
        "meta_decision": (state.get("meta_decision") or {}).get("decision")}
    if state.get("problem_spec_policy", {}).get("enabled") is True:
        ledger = state.get("obligation_ledger", [])
        summary["root_obligations"] = {
            "covered": sum(item.get("status") == "satisfied" for item in ledger),
            "total": len(ledger),
            "items": [
                {"ordinal": index, "type": item.get("obligation_type"),
                 "status": item.get("status", "open")}
                for index, item in enumerate(ledger, 1)
            ],
        }
        summary["plan_history"] = _plan_history(state)
    if "reasoner_checkpoints" in state:
        summary["reasoner_checkpoints"] = [
            {"round": item.get("round"), "status": item.get("status")}
            for item in state.get("reasoner_checkpoints", [])
            if isinstance(item, dict)
        ]
    if state.get("proof_graph_policy", {}).get("enabled") is True:
        from .solver_harness.proof_graph_projection import proof_graph_summary

        graph = proof_graph_summary(state)
        if graph is not None:
            summary["proof_graph"] = graph
    return summary


def _plan_history(state):
    """Return version-only history for archived and current plans."""
    history = []
    seen_attempts = set()
    step_counts = {}
    failures = state.get("failure_records", [])
    failures = failures if isinstance(failures, list) else []
    current_plan = state.get("plan")
    current_version = state.get("plan_version")

    for failure in failures:
        if not isinstance(failure, dict):
            continue
        archived = failure.get("archived_plan")
        if not isinstance(archived, dict):
            continue
        version = archived.get("version", failure.get("plan_version"))
        steps = archived.get("steps")
        if type(version) is int and version >= 1 and isinstance(steps, list):
            step_counts[version] = len(steps)
    if isinstance(current_plan, dict):
        steps = current_plan.get("steps")
        if type(current_version) is int and current_version >= 1 and isinstance(steps, list):
            step_counts[current_version] = len(steps)

    for failure in failures:
        if not isinstance(failure, dict):
            continue
        plan = failure.get("archived_plan")
        kind = failure.get("kind")
        version = (
            plan.get("version", failure.get("plan_version"))
            if isinstance(plan, dict)
            else failure.get("plan_version")
        )
        attempt = failure.get("attempt_index")
        if (type(version) is not int or version < 1
                or type(attempt) is not int or attempt < 0):
            continue
        if kind == "trace_back":
            status = "retried"
        elif isinstance(plan, dict):
            status = "archived"
        else:
            continue
        identity = (version, attempt)
        if identity in seen_attempts:
            continue
        steps = plan.get("steps") if isinstance(plan, dict) else None
        step_count = len(steps) if isinstance(steps, list) else step_counts.get(version)
        history.append({
            "plan_version": version,
            "attempt_index": attempt,
            "status": status,
            "step_count": step_count,
            "outcome": kind if kind in {
                "replan", "problem_spec_change", "trace_back",
            } else None,
        })
        seen_attempts.add(identity)

    plan = current_plan
    if isinstance(plan, dict):
        version = current_version if type(current_version) is int else plan.get("version")
        attempt = state.get("attempt_index")
        identity = (version, attempt)
        if (type(version) is int and version >= 1
                and type(attempt) is int and attempt >= 0
                and identity not in seen_attempts):
            steps = plan.get("steps")
            history.append({
                "plan_version": version,
                "attempt_index": attempt,
                "status": "current",
                "step_count": len(steps) if isinstance(steps, list) else 0,
                "outcome": None,
            })
    return history
