"""Persistent event-to-snapshot evolution for the versioned proof graph."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy

from .proof_graph import (
    ATTEMPT_STATES,
    PROPOSITION_STATES,
    ProofGraphValidationError,
    _attempt_id,
    _digest,
    _resolution_valid,
    _source_refs,
    proposition_id,
)
from .proof_graph_sources import (
    counterexample_attempts,
    dependency_closure,
    importable_ledger_rows,
    reasoner_report_call,
    verified_counterexample_receipt,
)
from .proof_graph_state import active_supports, validate_acyclic_graph


def evolve_proof_graph(
    state: Mapping,
    event: Mapping,
    persisted_receipts: Mapping[str, Mapping] | None = None,
) -> tuple[dict | None, dict | None]:
    """Derive one atomic immutable graph snapshot from the CAS candidate state."""
    policy = state.get("proof_graph_policy")
    graph = state.get("proof_graph")
    if (not isinstance(policy, Mapping) or policy.get("enabled") is not True
            or not isinstance(graph, Mapping)):
        return None, None
    snapshots = graph.get("snapshots")
    if not isinstance(snapshots, list) or not snapshots or not isinstance(snapshots[-1], Mapping):
        raise ProofGraphValidationError("missing_current_snapshot")
    previous = snapshots[-1]
    snapshot_versions = [
        item.get("graph_version") for item in snapshots if isinstance(item, Mapping)
    ]
    if (type(graph.get("current_version")) is not int
            or graph.get("current_version") < 0
            or len(snapshot_versions) != len(snapshots)
            or snapshot_versions != list(range(len(snapshots)))
            or graph.get("current_version") != snapshot_versions[-1]):
        raise ProofGraphValidationError("invalid_graph_version_history")
    previous_props = previous.get("propositions", {})
    previous_attempts = previous.get("attempts", {})
    ledger = state.get("verified_results_ledger", [])
    if not isinstance(ledger, list):
        raise ProofGraphValidationError("invalid_verified_ledger")

    candidate_rows, rejected = importable_ledger_rows(state, ledger)
    prior_bindings = {item.get("result_id"): item.get("ledger_dependencies")
                      for item in previous.get("derivations", {}).values()}
    for row, _source in candidate_rows:
        if row["result_id"] in prior_bindings and prior_bindings[row["result_id"]] != row.get("dependencies", []):
            raise ProofGraphValidationError("historical_dependencies_changed")
    graph_data = deepcopy(dict(previous))
    graph_data["graph_version"] = graph["current_version"]
    graph_data["bootstrap_complete"] = True
    graph_data["not_imported_records"].extend(rejected)
    prior_result_props = {
        item.get("result_id"): item.get("conclusion")
        for item in previous.get("derivations", {}).values()
        if isinstance(item, Mapping) and isinstance(item.get("result_id"), str)
    }
    rejected_ids = {
        item.get("source_id") for item in rejected
        if isinstance(item, Mapping) and isinstance(item.get("source_id"), str)
    }
    candidate_rows, dependency_rejections = dependency_closure(
        candidate_rows, rejected_ids=rejected_ids, known_ids=set(prior_result_props)
    )
    if previous.get("bootstrap_complete") is True and dependency_rejections:
        previous_ids = set(prior_result_props)
        if any(item.get("source_id") not in previous_ids for item in dependency_rejections):
            raise ProofGraphValidationError("illegal_new_graph_dependency")
    graph_data["not_imported_records"].extend(dependency_rejections)
    candidate_result_ids = {row["result_id"] for row, _source in candidate_rows}
    for derivation in graph_data["derivations"].values():
        attempt = graph_data["attempts"].get(derivation.get("attempt_id"), {})
        result_id = derivation.get("result_id")
        if (derivation.get("status") == "accepted"
                and attempt.get("direction") == "support"
                and isinstance(result_id, str) and result_id not in candidate_result_ids):
            derivation["status"] = "invalidated"
            attempt["status"] = "invalidated"

    imported_props: dict[str, str] = {}
    step_props: dict[str, set[str]] = {}
    seen_attempts: set[tuple[str, str]] = set()
    for row, source in candidate_rows:
        result_id = row["result_id"]
        prop_id = proposition_id(state, row["statement"], row["scope"])
        dependencies = row.get("dependencies", [])
        if (not isinstance(dependencies, list)
                or any(not isinstance(dep, str) for dep in dependencies)):
            graph_data["not_imported_records"].append(
                {"source_id": result_id, "reason": "invalid_dependencies"}
            )
            continue
        premises = []
        for dependency in dependencies:
            parent = imported_props.get(dependency, prior_result_props.get(dependency))
            if parent is None and len(step_props.get(dependency, set())) == 1:
                parent = next(iter(step_props[dependency]))
            if parent is None:
                premises = []
                break
            parent_node = graph_data["propositions"].get(parent, {})
            if parent_node.get("problem_version") != state.get("specification_version", 0):
                premises = []
                graph_data["not_imported_records"].append(
                    {"source_id": result_id, "reason": "cross_version_dependency"}
                )
                break
            if parent_node.get("conflict") is True:
                premises = []
                break
            premises.append(parent)
        if dependencies and not premises:
            graph_data["not_imported_records"].append(
                {"source_id": result_id, "reason": "unmapped_dependency"}
            )
            continue
        if prop_id in premises:
            graph_data["not_imported_records"].append(
                {"source_id": result_id, "reason": "cyclic_dependency"}
            )
            continue
        attempt_key = (source["report_call_id"], prop_id)
        if attempt_key in seen_attempts:
            graph_data["not_imported_records"].append(
                {"source_id": result_id, "reason": "duplicate_attempt_for_proposition"}
            )
            continue
        seen_attempts.add(attempt_key)
        item_sources = _source_refs(graph_data["sources"], [
            ("report", source["report_call_id"], row["evidence_level"]),
            ("review", source["review_call_id"], row["evidence_level"]),
            *(('receipt', receipt_id, "tool_verified") for receipt_id in source["receipt_ids"]),
        ])
        prop = graph_data["propositions"].setdefault(prop_id, {
            "id": prop_id,
            "statement": row["statement"],
            "scope": row["scope"],
            "problem_version": state.get("specification_version", 0),
            "status": "unresolved",
            "conflict": False,
            "sources": [],
        })
        prop["sources"] = sorted(set([*prop["sources"], *item_sources]))
        attempt_id = _attempt_id(state["run_id"], source["report_call_id"], prop_id)
        old_attempt = previous_attempts.get(attempt_id, {})
        attempt_status = "accepted"
        if isinstance(old_attempt, Mapping) and old_attempt.get("status") in {"invalidated", "rejected"}:
            attempt_status = old_attempt["status"]
        direction = "support"
        graph_data["attempts"][attempt_id] = {
            "id": attempt_id,
            "status": attempt_status,
            "direction": direction,
            "grade": row["evidence_level"],
            "conclusion": prop_id,
            "premises": premises,
            "source_refs": item_sources,
            "result_id": result_id,
            "lineage": row.get("lineage"),
        }
        derivation_id = "derivation_" + _digest(state["run_id"], result_id)[:32]
        graph_data["derivations"][derivation_id] = {
            "ledger_dependencies": list(dependencies),
            "id": derivation_id,
            "status": attempt_status,
            "grade": row["evidence_level"],
            "conclusion": prop_id,
            "premises": premises,
            "attempt_id": attempt_id,
            "source_refs": item_sources,
            "result_id": result_id,
        }
        imported_props[result_id] = prop_id
        step_props.setdefault(row["source"], set()).add(prop_id)

    # Carry model proposals from the same persisted reasoner reports, never accepting them.
    for step_id, step in state.get("steps", {}).items():
        report = step.get("report") if isinstance(step, Mapping) else None
        plan = state.get("plan")
        if not isinstance(report, Mapping) or not isinstance(plan, Mapping):
            continue
        plan_step = next((item for item in plan.get("steps", [])
                          if item.get("step_id") == step_id), None)
        if not isinstance(plan_step, Mapping):
            continue
        report_call_id = reasoner_report_call(
            state, step_id, report, plan.get("version", 0), state.get("attempt_index", 0)
        )
        if report_call_id is None:
            continue
        scope = plan_step.get("objective")
        if not isinstance(scope, str) or not scope.strip():
            continue
        for claim in report.get("claims", []):
            statement = claim.get("statement") if isinstance(claim, Mapping) else None
            if not isinstance(statement, str) or not statement.strip():
                continue
            prop_id = proposition_id(state, statement, scope)
            if prop_id not in graph_data["propositions"]:
                graph_data["propositions"][prop_id] = {
                    "id": prop_id, "statement": statement, "scope": scope,
                    "problem_version": state.get("specification_version", 0),
                    "status": "unresolved", "conflict": False, "sources": [],
                }
            attempt_id = _attempt_id(state["run_id"], report_call_id, prop_id)
            if attempt_id in graph_data["attempts"]:
                continue
            prior_lineage = next((item["id"] for item in previous_attempts.values()
                                  if isinstance(item, Mapping) and item.get("conclusion") == prop_id), None)
            graph_data["attempts"][attempt_id] = {
                "id": attempt_id,
                "status": "proposed",
                "direction": "support", "grade": None, "conclusion": prop_id,
                "premises": [],
                "source_refs": _source_refs(graph_data["sources"],
                                             [("report", report_call_id, "llm_reviewed")]),
                "result_id": None, "lineage": prior_lineage,
            }

    persisted_receipts = persisted_receipts or {}
    for candidate in counterexample_attempts(state, proposition_id):
        graph_data["propositions"].setdefault(candidate["conclusion"], {
            "id": candidate["conclusion"],
            "statement": candidate["claim"],
            "scope": candidate["scope"],
            "problem_version": state.get("specification_version", 0),
            "status": "unresolved",
            "conflict": False,
            "sources": [],
        })
        previous_id = candidate["attempt_id"]
        previous_attempt = previous_attempts.get(previous_id, {})
        receipt_id = (event.get("receipt_id") if isinstance(event, Mapping)
                      and event.get("type") == "proof_graph_counterexample_verified"
                      and event.get("attempt_id") == previous_id
                      else previous_attempt.get("result_id")
                      if isinstance(previous_attempt, Mapping) else None)
        receipt = verified_counterexample_receipt(
            state, candidate, receipt_id, persisted_receipts
        )
        if receipt is not None and candidate["status"] == "proposed":
            candidate.update(status="accepted", grade="tool_verified", result_id=receipt_id)
            candidate["source_refs"].append(f"receipt:{receipt_id}")
        if previous_id in graph_data["attempts"]:
            old = graph_data["attempts"][previous_id]
            if old.get("status") in {"invalidated", "rejected"}:
                candidate["status"] = old["status"]
            elif old.get("status") == "accepted" and receipt is None:
                candidate.update(
                    status="invalidated", result_id=old.get("result_id"),
                    source_refs=sorted(set([*old.get("source_refs", []), *candidate["source_refs"]])),
                )
            graph_data["attempts"][previous_id] = {**old, **candidate}
            for source_id in candidate["source_refs"]:
                graph_data["sources"].setdefault(source_id, {
                    "kind": source_id.split(":", 1)[0], "grade": candidate.get("grade")
                })
            continue
        graph_data["attempts"][previous_id] = candidate
        for source_id in candidate["source_refs"]:
            graph_data["sources"].setdefault(source_id, {
                "kind": source_id.split(":", 1)[0], "grade": candidate.get("grade")
            })

    try:
        validate_acyclic_graph(graph_data["propositions"], graph_data["derivations"])
    except ValueError as exc:
        raise ProofGraphValidationError(str(exc)) from exc

    if isinstance(event, Mapping) and event.get("type") == "proof_graph_counterexample_verified":
        attempt = graph_data["attempts"].get(event.get("attempt_id"))
        if (not isinstance(attempt, Mapping) or attempt.get("direction") != "counterexample"
                or attempt.get("status") != "accepted"
                or attempt.get("result_id") != event.get("receipt_id")):
            raise ProofGraphValidationError("invalid_counterexample_receipt")

    support_attempts = {
        key: item for key, item in graph_data["attempts"].items()
        if isinstance(item, Mapping) and item.get("direction") == "support"
    }
    support_candidates = active_supports(
        graph_data["propositions"], support_attempts, graph_data["derivations"]
    )
    resolution = event.get("resolution") if isinstance(event, Mapping) else None
    resolved_prop_id = None
    if isinstance(event, Mapping) and event.get("type") == "proof_graph_conflict_reviewed":
        resolved_prop_id = resolution.get("proposition_id") if isinstance(resolution, Mapping) else None
        if not isinstance(resolved_prop_id, str):
            raise ProofGraphValidationError("invalid_conflict_review")
        node = graph_data["propositions"].get(resolved_prop_id)
        counterexamples = [item for item in graph_data["attempts"].values()
                           if item.get("conclusion") == resolved_prop_id
                           and item.get("direction") == "counterexample"
                           and item.get("status") == "accepted"]
        is_conflict = isinstance(node, Mapping) and (
            node.get("conflict") is True
            or (resolved_prop_id in support_candidates and bool(counterexamples))
        )
        if (not isinstance(resolution, Mapping) or not is_conflict
                or resolution.get("ruling") not in {"support", "refutation"}
                or not _resolution_valid(state, resolved_prop_id, resolution)):
            raise ProofGraphValidationError("invalid_conflict_review")
        if resolution["ruling"] == "support":
            for attempt in graph_data["attempts"].values():
                if (attempt.get("conclusion") == resolved_prop_id
                        and attempt.get("direction") == "counterexample"
                        and attempt.get("status") in {"accepted", "invalidated"}):
                    attempt["status"] = "rejected"
        else:
            for derivation in graph_data["derivations"].values():
                if derivation.get("conclusion") == resolved_prop_id:
                    graph_data["attempts"][derivation["attempt_id"]]["status"] = "rejected"
                    derivation["status"] = "rejected"
        graph_data["propositions"][resolved_prop_id]["conflict"] = False
        graph_data["conflict_resolutions"][resolved_prop_id] = dict(resolution)

    for prop_id, prop in graph_data["propositions"].items():
        counterexamples = [item for item in graph_data["attempts"].values()
                           if item.get("conclusion") == prop_id
                           and item.get("direction") == "counterexample"
                           and item.get("status") == "accepted"]
        previously_conflicted = (
            isinstance(previous_props.get(prop_id), Mapping)
            and previous_props[prop_id].get("conflict") is True
        )
        prop["conflict"] = False if prop_id == resolved_prop_id else previously_conflicted or (
            prop_id in support_candidates and bool(counterexamples)
        )
        if prop["conflict"] and not previously_conflicted:
            prop["conflict_since_revision"] = state["state_revision"] + 1

    # Compute the whole AND/OR fixed point before changing any attempt state.
    active_props = active_supports(
        graph_data["propositions"], graph_data["attempts"], graph_data["derivations"]
    )
    for derivation in graph_data["derivations"].values():
        attempt = graph_data["attempts"].get(derivation["attempt_id"], {})
        if (attempt.get("status") == "accepted"
                and attempt.get("direction") == "support"
                and not all(parent in active_props for parent in derivation["premises"])):
            attempt["status"] = "invalidated"
            derivation["status"] = "invalidated"

    for prop_id, prop in graph_data["propositions"].items():
        support_ids = [item["attempt_id"] for item in graph_data["derivations"].values()
                       if item["conclusion"] == prop_id and item["status"] == "accepted"]
        counterexamples = [item for item in graph_data["attempts"].values()
                           if item["conclusion"] == prop_id
                           and item["direction"] == "counterexample"
                           and item["status"] == "accepted"]
        had_support = (isinstance(previous_props.get(prop_id), Mapping)
                       and previous_props[prop_id].get("status") in {"supported", "invalidated"})
        if prop.get("conflict") and support_ids:
            prop["status"] = "supported"
        elif prop_id in active_props:
            prop["status"] = "supported"
        elif counterexamples:
            prop["status"] = "refuted"
        elif had_support or (isinstance(previous_props.get(prop_id), Mapping)
                             and previous_props[prop_id].get("status") == "refuted"):
            prop["status"] = "invalidated"
        else:
            prop["status"] = "unresolved"
    for prop in graph_data["propositions"].values():
        if prop["status"] not in PROPOSITION_STATES:
            raise ProofGraphValidationError("invalid_proposition_status")
    for attempt in graph_data["attempts"].values():
        if attempt["status"] not in ATTEMPT_STATES:
            raise ProofGraphValidationError("invalid_attempt_status")

    graph_data["not_imported_records"] = list({
        (str(item.get("source_id")), str(item.get("reason"))): item
        for item in graph_data["not_imported_records"] if isinstance(item, Mapping)
    }.values())
    graph_data["not_imported_records"].sort(
        key=lambda item: (str(item.get("source_id")), str(item.get("reason")))
    )
    comparable = {key: value for key, value in graph_data.items() if key != "graph_version"}
    previous_comparable = {key: value for key, value in previous.items() if key != "graph_version"}
    if comparable == previous_comparable:
        return None, None
    version = graph.get("current_version", -1) + 1
    if type(version) is not int or version < 1:
        raise ProofGraphValidationError("invalid_graph_version")
    graph_data["graph_version"] = version
    next_graph = {
        "current_version": version,
        "snapshots": [*deepcopy(snapshots), graph_data],
    }
    summary = {
        "graph_version": version,
        "proposition_count": len(graph_data["propositions"]),
        "derivation_count": len(graph_data["derivations"]),
        "attempt_count": len(graph_data["attempts"]),
        "not_imported_count": len(graph_data["not_imported_records"]),
    }
    return next_graph, summary
