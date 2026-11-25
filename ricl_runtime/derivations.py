"""Run-local propositions supported by independently checked scoped derivations."""

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any

from .identity import stable_id


@dataclass(frozen=True)
class DerivationScope:
    domain: str = "reals"
    assumptions: frozenset[str] = frozenset()

    def includes(self, required: "DerivationScope") -> bool:
        return self.domain == required.domain and required.assumptions <= self.assumptions

    def public(self) -> dict[str, Any]:
        return {"domain": self.domain, "assumptions": sorted(self.assumptions)}


@dataclass(frozen=True)
class ScopedDerivation:
    proposition_id: str
    derivation_id: str
    evidence_id: str
    goal_id: str | None
    scope: DerivationScope
    premise_ids: tuple[str, ...]
    request_id: str
    method: str
    _check: dict[str, Any] = field(repr=False)

    @property
    def kind(self) -> str:
        return self._check["kind"]

    @property
    def check(self) -> dict[str, Any]:
        return deepcopy(self._check)

    def public(self) -> dict[str, Any]:
        return {
            "proposition_id": self.proposition_id,
            "derivation_id": self.derivation_id,
            "evidence_id": self.evidence_id,
            "goal_id": self.goal_id,
            "scope": self.scope.public(),
            "premise_ids": list(self.premise_ids),
            "request_id": self.request_id,
            "kind": self.kind,
            "method": self.method,
        }


@dataclass(frozen=True)
class DerivationChange:
    revoked_evidence_id: str
    invalidated_evidence_ids: tuple[str, ...]
    lost_proposition_ids: tuple[str, ...]
    reopened_goal_ids: tuple[str, ...]

    def public(self) -> dict[str, Any]:
        return asdict(self)


class ScopedDerivationGraph:
    """Keep AND premises at proposition level and alternative supports distinct."""

    def __init__(self) -> None:
        self._supports: dict[str, ScopedDerivation] = {}
        self._revoked: set[str] = set()
        self._active: set[str] = set()

    def fork(self) -> "ScopedDerivationGraph":
        branch = ScopedDerivationGraph()
        branch._supports = self._supports.copy()
        branch._revoked = self._revoked.copy()
        branch._active = self._active.copy()
        return branch

    def add(
        self,
        check: dict[str, Any],
        *,
        criterion_goal_id: str,
        scope: DerivationScope,
        premise_ids: tuple[str, ...],
        method: str,
        request_id: str,
    ) -> ScopedDerivation | None:
        """Register one independently verified derivation with available premises."""
        if check["status"] != "verified":
            return None
        proposition_id = stable_id(
            "proposition", {"criterion_goal": criterion_goal_id, "claim": check["evidence"]},
        )
        available = {support.proposition_id for support in self.applicable(scope)}
        if proposition_id in premise_ids or not available.issuperset(premise_ids):
            return None
        premise_ids = tuple(sorted(set(premise_ids)))
        derivation_id = stable_id("derivation", {
            "proposition_id": proposition_id,
            "scope": scope.public(),
            "premise_ids": premise_ids,
            "method": method,
        })
        evidence_id = stable_id("evidence", {"derivation": derivation_id, "check": check["evidence_id"]})
        if evidence_id in self._supports:
            return None
        support = ScopedDerivation(
            proposition_id, derivation_id, evidence_id, check["goal_id"], scope, premise_ids,
            request_id, method, {
                **deepcopy(check), "evidence_id": evidence_id, "proposition_id": proposition_id,
                "derivation_id": derivation_id, "premise_ids": list(premise_ids),
            },
        )
        self._supports[evidence_id] = support
        self._refresh()
        return support

    def active(self) -> tuple[ScopedDerivation, ...]:
        return tuple(support for eid, support in self._supports.items() if eid in self._active)

    def applicable(self, scope: DerivationScope) -> tuple[ScopedDerivation, ...]:
        return tuple(support for support in self.active() if scope.includes(support.scope))

    def goal_supports(self, scope: DerivationScope) -> dict[str, tuple[ScopedDerivation, ...]]:
        supports: dict[str, list[ScopedDerivation]] = {}
        for support in self.applicable(scope):
            if support.goal_id is not None:
                supports.setdefault(support.goal_id, []).append(support)
        return {goal: tuple(items) for goal, items in supports.items()}

    def revoke(self, evidence_id: str, *, scope: DerivationScope) -> DerivationChange | None:
        """Withdraw one checked basis and recompute conclusions from surviving bases."""
        if evidence_id not in self._supports or evidence_id in self._revoked:
            return None
        active_before = self._active
        propositions_before = {support.proposition_id for support in self.applicable(scope)}
        goals_before = self.goal_supports(scope)
        self._revoked.add(evidence_id)
        self._refresh()
        return DerivationChange(
            evidence_id,
            tuple(sorted(active_before - self._active)),
            tuple(sorted(propositions_before - {support.proposition_id for support in self.applicable(scope)})),
            tuple(sorted(goals_before.keys() - self.goal_supports(scope).keys())),
        )

    def _refresh(self) -> None:
        # Ground each proof in the scopes of already established premises.
        # Starting with no facts prevents cyclic support from keeping itself valid.
        active: set[str] = set()
        available: dict[str, set[DerivationScope]] = {}
        while True:
            previous_size = len(active)
            for evidence_id, support in self._supports.items():
                if evidence_id in self._revoked or evidence_id in active:
                    continue
                if all(any(support.scope.includes(premise_scope)
                           for premise_scope in available.get(premise, ()))
                       for premise in support.premise_ids):
                    active.add(evidence_id)
                    available.setdefault(support.proposition_id, set()).add(support.scope)
            if len(active) == previous_size:
                self._active = active
                return

    def public_snapshot(self, scope: DerivationScope) -> dict[str, Any]:
        propositions: dict[str, list[str]] = {}
        for support in self._supports.values():
            propositions.setdefault(support.proposition_id, []).append(support.derivation_id)
        return {
            "supports": [
                {
                    **support.public(),
                    "valid": eid in self._active,
                    "applicable": eid in self._active and scope.includes(support.scope),
                    "revoked": eid in self._revoked,
                }
                for eid, support in self._supports.items()
            ],
            "propositions": [
                {"proposition_id": proposition, "support_ids": support_ids}
                for proposition, support_ids in propositions.items()
            ],
            "goal_supports": {
                goal: [support.derivation_id for support in supports]
                for goal, supports in self.goal_supports(scope).items()
            },
        }
