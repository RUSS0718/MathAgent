"""S04 policy primitives; method names are a closed controller vocabulary."""

METHOD_IDS = frozenset({"direct", "contradiction", "induction", "construction", "computation", "unknown"})


def normalize_method(value):
    return value if isinstance(value, str) and value in METHOD_IDS else "unknown"


def action_keys(state, step_id):
    step = next((item for item in state.get("plan", {}).get("steps", [])
                 if item.get("step_id") == step_id), {})
    method = normalize_method(step.get("method_id"))
    roots = step.get("obligation_ids", []) or step.get("auxiliary_goal_ids", []) or ["unknown_target"]
    return [f"{root}:{method}" for root in sorted(roots)]


def review_progress(state, event, updates):
    """Reduce completed reviews in the same CAS transaction as their evidence.

    Admit newly satisfied roots and accepted prerequisite goals from the frozen
    specification. Free-form auxiliary statements cannot mint progress.
    """
    if (state.get("progress_policy") != {"enabled": True, "version": "progress-v1"}
            or event.get("type") != "step_reviewed"
            or event.get("valid") is False):
        return {}
    previous = state.get("progress", {})
    seen = set(previous.get("seen_roots", []))
    seen_goals = set(previous.get("seen_goals", []))
    new_goals = accepted_prerequisite_goals(state, event, updates) - seen_goals
    satisfied = {item["obligation_id"] for item in updates.get(
        "obligation_ledger", state.get("obligation_ledger", []))
        if item.get("status") == "satisfied"}
    # History is monotonic across invalidation and rollback: re-covering an old
    # root is necessary for correctness but cannot refresh the search allowance.
    fresh = satisfied - seen
    counts = dict(previous.get("action_failures", {}))
    blocked = set(previous.get("blocked_actions", []))
    keys = action_keys(state, event.get("step_id"))
    changed_targets = fresh | new_goals | {
        root for root, goals in prerequisite_goals(state).items() if goals & new_goals
    }
    if fresh or new_goals:
        counts = {key: value for key, value in counts.items()
                  if not (new_goals and key in keys)
                  and not any(key.startswith(f"{root}:") for root in changed_targets)}
        blocked = {key for key in blocked
                   if not (new_goals and key in keys)
                   and not any(key.startswith(f"{root}:") for root in changed_targets)}
    else:
        for key in keys:
            counts[key] = counts.get(key, 0) + 1
            if counts[key] >= 2:
                blocked.add(key)
    rounds = 0 if fresh or new_goals else previous.get("no_evidence_rounds", 0) + 1
    trigger = "stagnation" if rounds >= 3 else "local_action_blocked" if blocked.intersection(keys) else None
    progress = {
        "rounds": previous.get("rounds", 0) + 1,
        "no_evidence_rounds": rounds,
        "seen_roots": sorted(seen | satisfied),
        "seen_goals": sorted(seen_goals | new_goals),
        "action_failures": counts,
        "blocked_actions": sorted(blocked),
        "trigger": trigger,
    }
    patch = {"progress": progress}
    if trigger and updates.get("phase") not in {"TERMINAL", "FINAL_GENERATE", "FINAL_REVIEW"}:
        patch["phase"] = "META_DECIDE"
        # The reviewed step owns the intervention even if the normal ACCEPT
        # transition would otherwise have advanced to an unrelated next step.
        patch["current_step"] = event.get("step_id")
    return patch


def guard_action(harness, run):
    """A Meta continuation cannot dispatch an already blocked action."""
    state = run["state"]
    if (state.get("phase") not in {"PLAN", "STEP_EXECUTE", "CHALLENGE"}
            or state.get("progress_policy", {}).get("enabled") is not True):
        return run
    progress = state.get("progress", {})
    reason = None
    if progress.get("no_evidence_rounds", 0) >= 3:
        reason = "progress_stagnation_stop"
    elif set(action_keys(state, state.get("current_step"))).intersection(
            progress.get("blocked_actions", [])):
        reason = "progress_action_blocked"
    if reason is None:
        return run
    from .finalize import finish

    return finish(harness, run, "partial_aborted", reason)


def accepted_prerequisite_goals(state, event, updates):
    """Count fixed specification goals only when an accepted report proves them.

    The relevance path is the explicit prerequisite relation, not prose or an
    untrusted reviewer-created label. No proof graph is introduced here.
    """
    step_id = event.get("step_id")
    record = updates.get("steps", {}).get(step_id, {})
    verdict = record.get("verification", {})
    if not (verdict.get("valid") is True and verdict.get("verdict") == "ACCEPT"):
        return set()
    relevant = set().union(*prerequisite_goals(state).values())
    step = next((item for item in state.get("plan", {}).get("steps", [])
                 if item.get("step_id") == step_id), {})
    return relevant.intersection(step.get("auxiliary_goal_ids", []))


def prerequisite_goals(state):
    spec = state.get("problem_spec", {})
    goals = {goal["goal_id"]: goal for goal in spec.get("auxiliary_goals", [])}
    by_root = {}
    for root in spec.get("root_obligations", []):
        relevant = set()
        pending = list(root.get("prerequisite_ids", root.get("dependencies", [])))
        while pending:
            goal_id = pending.pop()
            if goal_id not in goals or goal_id in relevant:
                continue
            relevant.add(goal_id)
            goal = goals[goal_id]
            pending.extend(goal.get("prerequisite_ids", goal.get("dependencies", [])))
        by_root[root["obligation_id"]] = relevant
    return by_root
