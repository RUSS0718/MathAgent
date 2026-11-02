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
    return {"plan_version": state.get("plan_version"),
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
