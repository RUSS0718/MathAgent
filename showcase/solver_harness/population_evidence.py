"""Dependency snapshots and provenance checks for concurrent route evidence."""

from copy import deepcopy


def capture_dependencies(state, adopted):
    """Freeze only the accepted mathematical results actually adopted by a route."""
    ids = set(adopted.get("adopted_result_ids", []))
    proposition_ids = set(adopted.get("adopted_proposition_ids", []))
    if not ids and not proposition_ids:
        ids.update(_plan_dependency_results(state, adopted))
    current = _current_propositions(state)
    records = []
    for item in state.get("verified_results_ledger", []):
        result_id = item.get("result_id")
        if result_id not in ids:
            continue
        prop_id = _proposition_for_result(state, item)
        if proposition_ids and prop_id not in proposition_ids:
            continue
        if not _valid_result(state, item, current):
            continue
        records.append(
            {
                "result_id": result_id,
                "proposition_id": prop_id,
                "specification_version": item.get("specification_version"),
                "evidence_ids": [
                    f"report:{_report_call_for(state, item)}",
                    f"review:{item.get('review_call_id')}",
                ],
            }
        )
    return sorted(records, key=lambda item: item["result_id"])


def prepare_adoption(parent, route_snapshot):
    """Return merged snapshot replacement fields and validated action dependencies.

    Every adopted result is revalidated against the parent's current ledger; unrelated
    graph-version changes do not become dependencies.
    """
    candidate_ids = {
        item.get("result_id")
        for item in parent.get("verified_results_ledger", [])
        if isinstance(item, dict) and isinstance(item.get("result_id"), str)
    }
    dependencies = (
        capture_dependencies(parent, {"adopted_result_ids": candidate_ids}) if candidate_ids else []
    )
    result_ids = {item["result_id"] for item in dependencies}
    proposition_ids = {item["proposition_id"] for item in dependencies}
    current = _current_propositions(parent)
    selected = []
    selected_keys = set()
    for item in parent.get("verified_results_ledger", []):
        result_id = item.get("result_id")
        key = (result_id, _proposition_for_result(parent, item))
        if (
            result_id in result_ids
            and key not in selected_keys
            and _valid_result(parent, item, current)
        ):
            selected.append(deepcopy(item))
            selected_keys.add(key)
    sources = {item.get("source") for item in selected}

    accepted_keys = {(item.get("source"), item.get("statement")) for item in selected}
    accepted_results = [
        deepcopy(item)
        for item in parent.get("accepted_results", [])
        if item.get("category") == "step_result"
        and (item.get("source"), item.get("statement")) in accepted_keys
    ]
    call_ids = {
        evidence_id.split(":", 1)[1]
        for dependency in dependencies
        for evidence_id in dependency["evidence_ids"]
    }
    call_ids.update(item.get("review_call_id") for item in selected)
    calls = {
        call_id: deepcopy(parent["calls"][call_id])
        for call_id in call_ids
        if call_id in parent.get("calls", {})
    }

    snapshot_steps = deepcopy(route_snapshot.get("steps", {}))
    snapshot_steps.update(
        {
            step_id: deepcopy(parent["steps"][step_id])
            for step_id in sources
            if step_id in parent.get("steps", {})
        }
    )
    snapshot_calls = deepcopy(route_snapshot.get("calls", {}))
    snapshot_calls.update(calls)

    patch = {
        "adopted_result_ids": sorted(result_ids),
        "adopted_proposition_ids": sorted(proposition_ids),
        "accepted_results": accepted_results,
        "verified_results_ledger": selected,
        "steps": snapshot_steps,
        "calls": snapshot_calls,
    }
    if dependencies:
        patch["proof_graph"] = deepcopy(parent.get("proof_graph"))
    return patch, dependencies


def validate_dependencies(state, dependencies):
    """Check adopted evidence at its proposition boundary, ignoring unrelated graph edits."""
    if not isinstance(dependencies, list):
        return False, "dependency_snapshot_invalid"
    current = _current_propositions(state)
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            return False, "dependency_snapshot_invalid"
        item = next(
            (
                record
                for record in state.get("verified_results_ledger", [])
                if record.get("result_id") == dependency.get("result_id")
            ),
            None,
        )
        if item is None or not _valid_result(state, item, current):
            return False, "adopted_evidence_changed"
        if _proposition_for_result(state, item) != dependency.get("proposition_id") or item.get(
            "specification_version"
        ) != dependency.get("specification_version"):
            return False, "adopted_evidence_changed"
        expected = {f"review:{item.get('review_call_id')}"}
        report_id = _report_call_for(state, item)
        if report_id:
            expected.add(f"report:{report_id}")
        if set(dependency.get("evidence_ids", [])) != expected:
            return False, "adopted_evidence_changed"
    return True, None


def merge_route_evidence(current_state, route, action, branch_snapshot):
    """Return an incremental, independently verified ledger patch from one completed action."""
    empty = {}
    owner = current_state.get("population", {}).get("owner")
    same_execution_owner = action.get("owner") == route.get("owner")
    execution_owner_matches = same_execution_owner and action.get("owner") == owner
    acceptance_owner_matches = same_execution_owner and (
        action.get("acceptance_owner") == owner and route.get("acceptance_owner") == owner
    )
    if owner is None or (not execution_owner_matches and not acceptance_owner_matches):
        return empty, _audit(False, "owner_epoch_mismatch")
    if action.get("status") != "completed" or action.get("route_id") != route.get("route_id"):
        return empty, _audit(False, "action_not_completed")
    if branch_snapshot.get("run_id") != current_state.get("run_id"):
        return empty, _audit(False, "run_identity_mismatch")
    valid, reason = validate_dependencies(current_state, action.get("dependencies", []))
    if not valid:
        return empty, _audit(False, reason)

    branch = branch_snapshot.get("state", {})
    branch_graph = _current_propositions(branch)
    accepted_events = [
        event
        for event in branch_snapshot.get("events", [])
        if event.get("type") == "step_reviewed" and event.get("verdict") == "ACCEPT"
    ]
    event_steps = {event.get("step_id") for event in accepted_events}
    existing = {item.get("result_id") for item in current_state.get("verified_results_ledger", [])}
    accepted = []
    report_ids, review_ids = set(), set()
    for item in branch.get("verified_results_ledger", []):
        if item.get("result_id") in existing or item.get("source") not in event_steps:
            continue
        if not _valid_result(branch, item, branch_graph, route, action):
            continue
        report_id = _report_call_for(branch, item)
        review_id = item.get("review_call_id")
        if not report_id or not review_id:
            continue
        accepted.append(deepcopy(item))
        report_ids.add(report_id)
        review_ids.add(review_id)

    existing_obligations = {
        item.get("evidence_id") for item in current_state.get("obligation_evidence_ledger", [])
    }
    obligation_additions = [
        deepcopy(item)
        for item in branch.get("obligation_evidence_ledger", [])
        if item.get("evidence_id") not in existing_obligations
        and item.get("source") in event_steps
        and _valid_obligation_evidence(branch, item)
        and obligation_claims_eligible(branch, item, current_state)
    ]
    if not accepted and not obligation_additions:
        return empty, _audit(False, "no_verified_incremental_evidence")
    for item in obligation_additions:
        review_id = item.get("review_call_id")
        report_id = _report_call_for(
            state=branch,
            result={
                "source": item.get("source"),
                "review_call_id": item.get("review_call_id"),
                "plan_version": item.get("plan_version"),
                "attempt_index": item.get("attempt_index"),
            },
        )
        if review_id:
            review_ids.add(review_id)
        if report_id:
            report_ids.add(report_id)
    accepted_steps = {record.get("source") for record in accepted} | {
        item.get("source") for item in obligation_additions
    }

    updates = {
        "verified_results_ledger": accepted,
        "accepted_results": [
            deepcopy(item)
            for item in branch.get("accepted_results", [])
            if item.get("source") in accepted_steps and item.get("category") == "step_result"
        ],
        "steps": {
            step_id: deepcopy(branch.get("steps", {})[step_id])
            for step_id in accepted_steps
            if step_id in branch.get("steps", {})
        },
        "plan": {
            **deepcopy(current_state.get("plan", {})),
            "steps": [
                *deepcopy(current_state.get("plan", {}).get("steps", [])),
                *[
                    deepcopy(item)
                    for item in branch.get("plan", {}).get("steps", [])
                    if item.get("step_id") in accepted_steps
                    and item.get("step_id")
                    not in {
                        old.get("step_id") for old in current_state.get("plan", {}).get("steps", [])
                    }
                ],
            ],
        },
    }
    if obligation_additions:
        updates["obligation_evidence_ledger"] = obligation_additions
        from .obligation_evidence import update_obligation_ledger

        candidate = {
            **current_state,
            "obligation_evidence_ledger": [
                *current_state.get("obligation_evidence_ledger", []),
                *obligation_additions,
            ],
        }
        updates["obligation_ledger"] = update_obligation_ledger(
            current_state["problem_spec"],
            current_state.get("obligation_ledger", []),
            candidate["obligation_evidence_ledger"],
        )
    return updates, {
        **_audit(True, None),
        "type": "step_reviewed",
        "source_event_ids": [
            event["event_id"] for event in accepted_events if event.get("step_id") in accepted_steps
        ],
        "report_call_ids": sorted(report_ids),
        "review_call_ids": sorted(review_ids),
        "merged_result_ids": [item["result_id"] for item in accepted],
        "merged_obligation_ids": sorted({item["obligation_id"] for item in obligation_additions}),
    }


def _valid_result(state, result, current, route=None, action=None):
    if (
        result.get("valid") is not True
        or result.get("proven") is not True
        or result.get("invalidated") is True
        or result.get("evidence_level") != "llm_reviewed"
        or not result.get("claim_indexes")
    ):
        return False
    if route is not None and result.get("plan_version") != route.get("plan_version"):
        return False
    if result.get("specification_version") != state.get("specification_version"):
        return False
    step = state.get("steps", {}).get(result.get("source"), {})
    if (
        step.get("verification", {}).get("valid") is not True
        or step.get("verification", {}).get("verdict") != "ACCEPT"
        or not isinstance(step.get("report"), dict)
    ):
        return False
    review = state.get("calls", {}).get(result.get("review_call_id"), {})
    if (
        review.get("role") != "step_verifier"
        or review.get("status") != "completed"
        or review.get("response", {}).get("verdict") != "ACCEPT"
    ):
        return False
    if not any(
        outcome.get("statement") == result.get("statement")
        and outcome.get("category") == result.get("category")
        and set(outcome.get("claim_indexes", [])) == set(result.get("claim_indexes", []))
        for outcome in review.get("response", {}).get("classified_outcomes", [])
        if isinstance(outcome, dict)
    ):
        return False
    if route is not None and (
        review.get("route_id") != route.get("route_id")
        or review.get("action_id") != action.get("action_id")
    ):
        return False
    report_id = _report_call_for(state, result)
    report = state.get("calls", {}).get(report_id, {})
    if (
        report.get("role") != "reasoner"
        or report.get("status") != "completed"
        or not isinstance(report.get("response", {}).get("claims"), list)
    ):
        return False
    if route is not None and (
        report.get("route_id") != route.get("route_id")
        or report.get("action_id") != action.get("action_id")
    ):
        return False
    for index in result["claim_indexes"]:
        claims = report["response"].get("claims", [])
        if type(index) is not int or index < 0 or index >= len(claims):
            return False
        if claims[index].get("statement") != result.get("statement"):
            return False
    prop_id = _proposition_for_result(state, result)
    prop = current.get(prop_id)
    if prop is None or prop.get("status") != "supported" or prop.get("conflict") is True:
        return False
    graph = state.get("proof_graph", {})
    snapshot = next(
        (
            item
            for item in graph.get("snapshots", [])
            if item.get("graph_version") == graph.get("current_version")
        ),
        None,
    )
    return bool(
        snapshot
        and any(
            derivation.get("result_id") == result.get("result_id")
            and derivation.get("status") == "accepted"
            and derivation.get("conclusion") == prop_id
            and f"review:{result.get('review_call_id')}" in derivation.get("source_refs", [])
            and f"report:{report_id}" in derivation.get("source_refs", [])
            for derivation in snapshot.get("derivations", {}).values()
        )
    )


def obligation_claims_eligible(state, evidence, graph_state=None):
    """Exclude obligation source claims contradicted by the current proof graph."""
    claims = state.get("steps", {}).get(evidence.get("source"), {}).get("report", {}).get("claims", [])
    indexes = evidence.get("claim_indexes", [])
    if not indexes or any(type(index) is not int or not 0 <= index < len(claims)
                          for index in indexes):
        return False
    current = _current_propositions(state if graph_state is None else graph_state)
    for index in indexes:
        prop = current.get(_proposition_for_result(state, claims[index]), {})
        if prop.get("conflict") is True or prop.get("status") == "refuted":
            return False
    return True


def _valid_obligation_evidence(state, evidence):
    import hashlib
    import json

    if (
        evidence.get("valid") is not True
        or evidence.get("invalidated") is True
        or evidence.get("run_id") != state.get("run_id")
        or evidence.get("specification_version") != state.get("specification_version")
        or not obligation_claims_eligible(state, evidence)
    ):
        return False
    step_id = evidence.get("source")
    step = state.get("steps", {}).get(step_id, {})
    review = state.get("calls", {}).get(evidence.get("review_call_id"), {})
    report = step.get("report", {})
    report_call_id = _report_call_for(
        state,
        {
            "source": step_id,
            "review_call_id": evidence.get("review_call_id"),
            "plan_version": evidence.get("plan_version"),
            "attempt_index": evidence.get("attempt_index"),
        },
    )
    report_call = state.get("calls", {}).get(report_call_id, {})
    report_digest = hashlib.sha256(
        json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return (
        step.get("verification", {}).get("valid") is True
        and step.get("verification", {}).get("verdict") == "ACCEPT"
        and review.get("role") == "step_verifier"
        and review.get("status") == "completed"
        and review.get("response", {}).get("verdict") == "ACCEPT"
        and report_call.get("status") == "completed"
        and evidence.get("source_report_sha256") == report_digest
        and any(
            item.get("obligation_id") == evidence.get("obligation_id")
            and item.get("evidence_category") == evidence.get("evidence_category")
            and item.get("claim_indexes") == evidence.get("claim_indexes")
            for item in review.get("response", {}).get("obligation_evidence", [])
            if isinstance(item, dict)
        )
    )


def _report_call_for(state, result):
    review = state.get("calls", {}).get(result.get("review_call_id"), {})
    candidates = []
    for call_id, record in state.get("calls", {}).items():
        request = record.get("request", {})
        step = request.get("step", {})
        step_id = step.get("step_id", request.get("step_id"))
        if (record.get("role") != "reasoner" or record.get("status") != "completed"
                or step_id != result.get("source")
                or record.get("plan_version") != result.get("plan_version")
                or record.get("attempt_index") != result.get("attempt_index")):
            continue
        if review and (any(record.get(key) != review.get(key) for key in ("route_id", "action_id"))
                       or record.get("request_revision", 0) > review.get("request_revision", 0)):
            continue
        claims = record.get("response", {}).get("claims", [])
        if all(type(index) is int and 0 <= index < len(claims)
               and claims[index].get("statement") == result.get("statement")
               for index in result.get("claim_indexes", [])):
            candidates.append((record.get("request_revision", 0), call_id))
    return max(candidates)[1] if candidates else None


def _proposition_for_result(state, result):
    from .proof_graph import proposition_id

    return proposition_id(state, result.get("statement", ""), result.get("scope", "problem"))


def _current_propositions(state):
    graph = state.get("proof_graph")
    snapshot = (
        next(
            (
                item
                for item in graph.get("snapshots", [])
                if item.get("graph_version") == graph.get("current_version")
            ),
            None,
        )
        if isinstance(graph, dict)
        else None
    )
    return {} if snapshot is None else snapshot.get("propositions", {})


def _plan_dependency_results(state, adopted):
    required = _plan_dependency_steps(state, adopted)
    return {
        item.get("result_id")
        for item in state.get("verified_results_ledger", [])
        if item.get("source") in required and isinstance(item.get("result_id"), str)
    }


def _plan_dependency_steps(state, adopted):
    plan = adopted.get("plan", state.get("plan", {}))
    steps = {item.get("step_id"): item for item in plan.get("steps", []) if isinstance(item, dict)}
    current = (
        adopted.get("current_step") if "current_step" in adopted else state.get("current_step")
    )
    if current not in steps:
        return set()
    required, pending = set(), list(steps[current].get("depends_on", []))
    while pending:
        step_id = pending.pop()
        if step_id in required:
            continue
        required.add(step_id)
        pending.extend(steps.get(step_id, {}).get("depends_on", []))
    return required


def _audit(accepted, reason):
    return {
        "accepted": accepted,
        "reason": reason,
        "merged_result_ids": [],
        "source_event_ids": [],
        "report_call_ids": [],
        "review_call_ids": [],
    }
