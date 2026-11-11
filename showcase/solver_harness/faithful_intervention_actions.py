"""Deterministic action priority from current obligations and audited costs."""

from dataclasses import asdict
from statistics import mean

from .progress import METHOD_IDS


def rank_actions(state, actions, *, observed_costs=None):
    """Keep unmeasured progress/risk unknown; never treat proposed benefit as proof."""
    open_roots = {item["obligation_id"] for item in state.get("obligation_ledger", [])
                  if item.get("status") != "satisfied"}
    steps = {item["step_id"]: item for item in (state.get("plan") or {}).get("steps", [])}
    items = []
    for action in actions:
        step = steps.get(action["target"], {})
        method = action.get("parameters", {}).get("method_id")
        costs = (observed_costs or {}).get(action["action_id"], [])
        items.append({
            "action_id": action["action_id"],
            "obligation_relevance": len(open_roots.intersection(step.get("obligation_ids", []))),
            "expected_verified_progress": None,
            "hypothesis_distinguishability": (int(method != step.get("method_id"))
                                               if isinstance(method, str)
                                               and method in METHOD_IDS and method != "unknown"
                                               and isinstance(step.get("method_id"), str) else None),
            "actual_token_cost": mean(item["tokens"] for item in costs) if costs else None,
            "cost_source_pair_ids": sorted({item["pair_id"] for item in costs}),
            "effective_evidence_risk": None,
            "acceptance_boundary": "no_parent_evidence_merge",
            "ranking_policy": "faithful-action-order-v1",
        })
    return sorted(items, key=lambda item: (
        -item["obligation_relevance"], item["hypothesis_distinguishability"] is None,
        -item["hypothesis_distinguishability"] if item["hypothesis_distinguishability"] is not None else 0,
        item["actual_token_cost"] is None,
        item["actual_token_cost"] if item["actual_token_cost"] is not None else float("inf"),
        item["action_id"],
    ))


def registered_action_ranking(engine, run, hypothesis):
    """Read only integrity-checked, same-checkpoint native cost observations."""
    costs = {}
    for row in engine._connection.execute("SELECT pair_id FROM faithful_intervention_pairs").fetchall():
        report = engine.get_pair(row[0])
        if (report["run_id"] != run["run_id"] or report["checkpoint_revision"] != run["state_revision"]
                or report.get("branch_engine") != "native_solver_checkpoint"):
            continue
        for outcome in report["arms"].values():
            tokens = outcome.get("cost", {}).get("provider_usage", {}).get("total_tokens")
            if (outcome.get("evidence_integrity") == "verified"
                    and type(tokens) is int and tokens >= 0):
                costs.setdefault(outcome["action_id"], []).append({"pair_id": report["pair_id"], "tokens": tokens})
    actions = [asdict(engine.get_action(key)) for key in hypothesis.candidate_action_ids]
    return rank_actions(run["state"], actions, observed_costs=costs)
