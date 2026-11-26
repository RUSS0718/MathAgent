"""Pure-Python 0-token APRS route scheduler and SharedReasoningState adapter for Track 1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .aprs import Candidate as AprsCandidate
from .aprs import VerifierEvidence, evaluate_fixed_candidates
from .identity import stable_id
from .reasoning_state import SharedReasoningState
from .track1_verification import L1_EVIDENCE, Lemma


class Track1SharedState:
    """Wrap SharedReasoningState to manage topological admission, invalidation, and failure constraints."""

    def __init__(self) -> None:
        self.srs = SharedReasoningState()
        self._pool: dict[str, tuple[str, str, str, str]] = {}
        self.failed_constraints: list[str] = []

    def _evict_invalidated(self, dropped_ids: set[str]) -> None:
        for key in [k for k, (_, _, eid, _) in self._pool.items() if eid in dropped_ids or not self.srs.is_valid(eid)]:
            del self._pool[key]

    def invalidate_claim(self, claim: str) -> tuple[str, ...]:
        """Invalidate any previously admitted pool lemma matching a refuted claim and propagate."""
        norm = "".join(claim.split())
        key = stable_id("lemma", norm)
        entry = self._pool.get(key)
        if entry is None:
            return ()
        dropped = self.srs.invalidate(entry[2])
        self._evict_invalidated(set(dropped))
        return dropped

    def admit_pruned(
        self,
        graph: tuple[Lemma, ...],
        retained: tuple[tuple[Lemma, str], ...],
        route_id: str,
    ) -> dict[str, str]:
        """Register retained L1/L2 lemmas in topological order under SharedReasoningState."""
        retained_map = {node.id: (node, evidence) for node, evidence in retained}
        local_to_srs: dict[str, str] = {}
        admitted: dict[str, str] = {}

        for node in graph:
            if node.check == "fail":
                self.invalidate_claim(node.claim)
                continue
            item = retained_map.get(node.id)
            if item is None:
                continue
            _, evidence = item
            key = stable_id("lemma", "".join(node.claim.split()))
            dep_ids = tuple(local_to_srs[p] for p in node.premises if p in local_to_srs)
            if any(not self.srs.is_valid(dep_id) for dep_id in dep_ids):
                continue

            existing = self._pool.get(key)
            if existing is not None and self.srs.is_valid(existing[2]):
                cur_claim, cur_ev, cur_eid, cur_route = existing
                local_to_srs[node.id] = cur_eid
                if evidence == L1_EVIDENCE and cur_ev != L1_EVIDENCE:
                    self._pool[key] = (cur_claim, L1_EVIDENCE, cur_eid, route_id)
                admitted[key] = self._pool[key][1]
                continue

            ev_obj = self.srs.add_verified_result(
                node.claim,
                scope=f"global:{evidence}",
                depends_on_all=dep_ids,
            )
            local_to_srs[node.id] = ev_obj.evidence_id
            self._pool[key] = (node.claim, evidence, ev_obj.evidence_id, route_id)
            admitted[key] = evidence

        return admitted

    def add_constraint(self, constraint: str) -> None:
        """Store up to 4 deduplicated failed-route constraints for cross-route guidance."""
        cleaned = constraint.strip()
        if cleaned and cleaned not in self.failed_constraints and len(self.failed_constraints) < 4:
            self.failed_constraints.append(cleaned)

    def active_pool(self) -> dict[str, tuple[str, str]]:
        """Return active valid lemmas as stable_id -> (claim, evidence_label)."""
        return {
            key: (claim, evidence)
            for key, (claim, evidence, eid, _) in self._pool.items()
            if self.srs.is_valid(eid)
        }

    def format_pool(self) -> str:
        """Render active shared lemmas for prompt injection."""
        return "\n".join(
            f"[{key}] [{evidence}] {claim}"
            for key, (claim, evidence) in self.active_pool().items()
        )

    def snapshot(self) -> dict[str, object]:
        """Return redacted counters suitable for trace logging."""
        valid = self.active_pool()
        return {
            "valid_count": len(valid),
            "constraints_count": len(self.failed_constraints),
            "srs_evidence_count": len(self.srs.valid_evidence()),
        }


@dataclass
class RouteState:
    """Track one candidate route trajectory, its verified progress, and spent tokens."""

    route_id: str
    strategy: str
    latest: Any
    reviewed: bool = False
    spent_tokens: int = 0
    l1_lemmas: int = 0
    l2_lemmas: int = 0
    repair_attempts: int = 0
    continue_attempts: int = 0
    exhausted: bool = False

    @property
    def verified_gain(self) -> int:
        return 2 * self.l1_lemmas + self.l2_lemmas

    @property
    def prefix_ratio(self) -> float:
        if self.reviewed and self.latest.steps:
            return self.latest.prefix / len(self.latest.steps)
        return 0.0

    @property
    def marginal_rate(self) -> float:
        return (self.verified_gain + self.prefix_ratio) / max(1.0, self.spent_tokens / 1000.0)

    @property
    def can_continue(self) -> bool:
        return (
            self.reviewed
            and not self.exhausted
            and self.continue_attempts == 0
            and self.repair_attempts == 0
            and self.latest.verdict == "incomplete"
            and self.latest.prefix > 0
            and (self.latest.answer is None or self.latest.prefix < len(self.latest.steps))
        )

    def can_repair(self, pool_nonempty: bool) -> bool:
        return (
            self.reviewed
            and not self.exhausted
            and self.repair_attempts == 0
            and self.latest.verdict == "fail"
            and self.latest.first_error > 0
            and (self.latest.prefix > 0 or self.verified_gain > 0 or pool_nonempty)
        )


def select_aprs_action(
    routes: list[RouteState],
    srs_state: Track1SharedState,
) -> tuple[str | None, str, dict[str, object]]:
    """Choose the next single-arm Track 1 action using 0-token APRS ranking."""
    pool = srs_state.active_pool()
    rates = {route.route_id: round(route.marginal_rate, 3) for route in routes}

    unreviewed = [route for route in routes if not route.reviewed]
    if unreviewed:
        target = max(
            unreviewed,
            key=lambda r: (r.latest.answer is not None, len(r.latest.steps), -r.spent_tokens),
        )
        return (
            target.route_id,
            "audit",
            {
                "priority_order": [r.route_id for r in unreviewed],
                "selected_route": target.route_id,
                "selected_action": "audit",
                "marginal_rates": rates,
                "srs_pool_size": len(pool),
                "route_count": len(routes),
            },
        )

    actionable = [r for r in routes if r.can_continue or r.can_repair(bool(pool))]
    if not actionable:
        return (
            None,
            "salvage_switch",
            {
                "priority_order": [],
                "selected_route": None,
                "selected_action": "salvage_switch",
                "marginal_rates": rates,
                "srs_pool_size": len(pool),
                "route_count": len(routes),
            },
        )

    aprs_candidates = tuple(
        AprsCandidate(
            candidate_id=r.route_id,
            novelty=1 if r.strategy == "salvage_switch" else 0,
            known_token_cost=max(1, r.spent_tokens),
        )
        for r in actionable
    )
    evidences: list[VerifierEvidence] = []
    for r in actionable:
        for i in range(r.l1_lemmas):
            evidences.append(
                VerifierEvidence(
                    candidate_id=r.route_id,
                    evidence_id=f"{r.route_id}:l1:{i}",
                    obligation_id=f"{r.route_id}:l1:{i}",
                    status="accepted",
                    valid=True,
                )
            )
        for i in range(r.l2_lemmas):
            evidences.append(
                VerifierEvidence(
                    candidate_id=r.route_id,
                    evidence_id=f"{r.route_id}:l2:{i}",
                    obligation_id=f"{r.route_id}:l2:{i}",
                    status="accepted",
                    valid=True,
                )
            )
        if r.latest.prefix > 0:
            evidences.append(
                VerifierEvidence(
                    candidate_id=r.route_id,
                    evidence_id=f"{r.route_id}:prefix",
                    obligation_id=f"{r.route_id}:prefix",
                    status="accepted",
                    valid=True,
                    evidence_kind="goal",
                )
            )

    aprs_report = evaluate_fixed_candidates(
        aprs_candidates,
        tuple(evidences),
        budget_snapshot={"srs_pool_size": len(pool), "route_count": len(routes)},
        tool_capabilities=(),
        verifier_capability="hybrid_l1_l2",
        aprs_enabled=True,
    )
    priority_order: list[str] = list(aprs_report["priority_order"])
    pareto_rank = {rid: idx for idx, rid in enumerate(priority_order)}
    top = min(actionable, key=lambda r: (pareto_rank[r.route_id], -r.marginal_rate))
    action = "continue" if top.can_continue else "pruned_repair"
    return (
        top.route_id,
        action,
        {
            "priority_order": priority_order,
            "selected_route": top.route_id,
            "selected_action": action,
            "marginal_rates": rates,
            "srs_pool_size": len(pool),
            "route_count": len(routes),
        },
    )
