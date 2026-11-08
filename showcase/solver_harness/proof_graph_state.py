"""Fixed-point support calculation for immutable proof-graph snapshots."""

from __future__ import annotations

from collections.abc import Mapping


def active_supports(propositions: Mapping, attempts: Mapping, derivations: Mapping) -> set[str]:
    """Return support reachable through accepted AND-premises, with OR conclusions."""
    blocked = {
        proposition for proposition, node in propositions.items()
        if (not isinstance(node, Mapping) or node.get("conflict") is True
            or node.get("status") == "refuted")
    }
    blocked.update(
        attempt.get("conclusion") for attempt in attempts.values()
        if isinstance(attempt, Mapping)
        and attempt.get("direction") == "counterexample"
        and attempt.get("status") == "accepted"
    )
    active: set[str] = set()
    changed = True
    while changed:
        changed = False
        for derivation in derivations.values():
            if not isinstance(derivation, Mapping) or derivation.get("status") != "accepted":
                continue
            attempt = attempts.get(derivation.get("attempt_id"), {})
            conclusion = derivation.get("conclusion")
            premises = derivation.get("premises")
            if (not isinstance(attempt, Mapping) or attempt.get("status") != "accepted"
                    or attempt.get("direction") != "support"
                    or conclusion in blocked or not isinstance(premises, list)
                    or any(parent in blocked or parent not in active for parent in premises)):
                continue
            if conclusion not in active:
                active.add(conclusion)
                changed = True
    return active


def validate_acyclic_graph(propositions: Mapping, derivations: Mapping) -> None:
    """Reject missing nodes and cycles before a snapshot can be persisted."""
    dependencies: dict[str, set[str]] = {key: set() for key in propositions}
    for derivation in derivations.values():
        if (not isinstance(derivation, Mapping)
                or derivation.get("conclusion") not in propositions
                or not isinstance(derivation.get("premises"), list)
                or any(item not in propositions for item in derivation["premises"])):
            raise ValueError("dangling_proposition_reference")
        dependencies[derivation["conclusion"]].update(derivation["premises"])
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(proposition: str) -> None:
        if proposition in visiting:
            raise ValueError("cyclic_dependency")
        if proposition in visited:
            return
        visiting.add(proposition)
        for parent in dependencies[proposition]:
            visit(parent)
        visiting.remove(proposition)
        visited.add(proposition)

    for proposition in dependencies:
        visit(proposition)
