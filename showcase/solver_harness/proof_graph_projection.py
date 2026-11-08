"""Public, text-free projections for the versioned proof graph."""

from __future__ import annotations

from collections.abc import Mapping

from .proof_graph import ATTEMPT_STATES, EVIDENCE_GRADES, PROPOSITION_STATES


def proof_graph_summary(state: Mapping, graph_version: int | None = None) -> dict | None:
    """Return one persisted graph version with generated IDs and an allowlist only."""
    graph = state.get("proof_graph") if isinstance(state, Mapping) else None
    if not isinstance(graph, Mapping):
        return None
    snapshots = graph.get("snapshots")
    if not isinstance(snapshots, list):
        return None
    requested = graph.get("current_version") if graph_version is None else graph_version
    if type(requested) is not int:
        return None
    snapshot = next((item for item in snapshots
                     if isinstance(item, Mapping) and item.get("graph_version") == requested), None)
    if snapshot is None:
        return None
    propositions = snapshot.get("propositions")
    attempts = snapshot.get("attempts")
    sources = snapshot.get("sources")
    if not all(isinstance(item, Mapping) for item in (propositions, attempts, sources)):
        return None

    prop_ids = sorted(propositions)
    attempt_ids = sorted(attempts)
    source_ids = sorted(sources)
    prop_alias = {raw: f"p{index}" for index, raw in enumerate(prop_ids, 1)}
    attempt_alias = {raw: f"a{index}" for index, raw in enumerate(attempt_ids, 1)}
    source_alias = {raw: f"source-{index}" for index, raw in enumerate(source_ids, 1)}

    def public_sources(refs: object) -> list[str]:
        if not isinstance(refs, list):
            return []
        return sorted({source_alias[ref] for ref in refs if ref in source_alias})

    public_attempts = []
    for raw_id in attempt_ids:
        item = attempts[raw_id]
        if not isinstance(item, Mapping):
            return None
        status = item.get("status")
        direction = item.get("direction")
        conclusion = item.get("conclusion")
        grade = item.get("grade")
        premises = item.get("premises", [])
        if (status not in ATTEMPT_STATES or direction not in {"support", "counterexample"}
                or conclusion not in prop_alias or not isinstance(premises, list)
                or any(premise not in prop_alias for premise in premises)
                or grade not in EVIDENCE_GRADES | {"mixed", None}):
            return None
        public_attempts.append({
            "id": attempt_alias[raw_id],
            "status": status,
            "direction": direction,
            "grade": grade,
            "conclusion": prop_alias[conclusion],
            "dependencies": [prop_alias[premise] for premise in premises],
            "sources": public_sources(item.get("source_refs")),
        })

    public_propositions = []
    for raw_id in prop_ids:
        item = propositions[raw_id]
        if not isinstance(item, Mapping):
            return None
        status = item.get("status")
        if status not in PROPOSITION_STATES or type(item.get("conflict")) is not bool:
            return None
        derivations = snapshot.get("derivations", {})
        supporting = [derivation for derivation in derivations.values()
                      if isinstance(derivation, Mapping)
                      and derivation.get("conclusion") == raw_id
                      and derivation.get("status") == "accepted"] if isinstance(derivations, Mapping) else []
        dependencies = sorted({premise for derivation in supporting
                                for premise in derivation.get("premises", [])
                                if premise in prop_alias})
        grades = {derivation.get("grade") for derivation in supporting
                  if derivation.get("grade") in EVIDENCE_GRADES}
        grade = next(iter(grades)) if len(grades) == 1 else "mixed" if grades else None
        refs = set(item.get("sources", []))
        for derivation in supporting:
            refs.update(derivation.get("source_refs", []))
        public_propositions.append({
            "id": prop_alias[raw_id],
            "status": status,
            "grade": grade,
            "conflict": item["conflict"],
            "dependencies": [prop_alias[raw] for raw in dependencies],
            "sources": public_sources(list(refs)),
        })

    return {
        "graph_version": requested,
        "propositions": public_propositions,
        "attempts": public_attempts,
    }
