"""Public exact excerpts of accepted proof-graph evidence for presentation."""

from .final_evidence import artifact_identity
from .redaction import redact_text
from .solver_harness.proof_graph_projection import proof_graph_summary
from .solver_harness.proof_graph_state import active_supports


def presentation_evidence(state, answer):
    public = proof_graph_summary(state)
    result = {"specification_version": state.get("specification_version"),
              "graph_version": public["graph_version"] if public else None,
              "sources": [], "verified_claims": []}
    if public is None:
        return result
    graph = next(item for item in state["proof_graph"]["snapshots"]
                 if item["graph_version"] == public["graph_version"])
    propositions, attempts, derivations = (graph[key] for key in ("propositions", "attempts", "derivations"))
    active = active_supports(propositions, attempts, derivations)
    prop_alias = {key: f"p{index}" for index, key in enumerate(sorted(propositions), 1)}
    attempt_alias = {key: f"a{index}" for index, key in enumerate(sorted(attempts), 1)}
    for key in sorted(propositions):
        node = propositions[key]
        text = node["statement"]
        # A graph statement can only be quoted here if already publicly delivered.
        if (key not in active or node["status"] != "supported" or not text
                or text != redact_text(text) or text not in answer):
            continue
        supports = [item for item in derivations.values()
                    if item["conclusion"] == key and item["status"] == "accepted"
                    and attempts[item["attempt_id"]]["status"] == "accepted"
                    and all(parent in active for parent in item["premises"])]
        sources = []
        for derivation in supports:
            alias = attempt_alias[derivation["attempt_id"]]
            sources.append({"id": f"inference:v{public['graph_version']}:{alias}",
                            "kind": "Inference", "node_id": alias, "grade": derivation["grade"],
                            "conclusion": prop_alias[key],
                            "dependencies": [prop_alias[parent] for parent in derivation["premises"]]})
        grades = {item["grade"] for item in sources}
        if not sources:
            continue
        alias = prop_alias[key]
        sources.insert(0, {"id": f"proposition:v{public['graph_version']}:{alias}",
                           "kind": "Proposition", "node_id": alias,
                           "grade": next(iter(grades)) if len(grades) == 1 else "mixed"})
        for source in sources:
            source.update({"scope": redact_text(node["scope"])[:200], "status": "current",
                           "target_type": "graph_statement",
                           "graph_version": public["graph_version"], "artifact": artifact_identity(text)})
        result["sources"].extend(sources)
        result["verified_claims"].append({"text": text, "claim_refs": [item["id"] for item in sources]})
    return result
