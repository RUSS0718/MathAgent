"""Select the next online route from surviving checks and settled usage."""

import json
from collections import Counter
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Literal

from .derivations import ScopedDerivation
from .identity import stable_id
from .port import ModelReply

OnlineSearchMode = Literal["aprs", "round_robin"]
_MAX_CANDIDATES = 3
_MAX_STRATEGY_CHARS = 300
_MAX_PROPOSAL_CHARS = 4096
_GAIN_SELECTIONS_BEFORE_EXPLORATION = 2

CANDIDATE_INSTRUCTIONS = (
    f'Propose 1 to {_MAX_CANDIDATES} distinct routes for solving the problem in order. '
    'Return only {"candidates": [{"strategy": "<one short public approach>"}]}. '
    f'Use 1 to {_MAX_STRATEGY_CHARS} characters per strategy. '
    'Give an approach for each route. Leave mathematical checks and answers for route expansion.'
)


@dataclass
class OnlineRoute:
    route_id: str
    strategy: str
    previous_answer: str = ""
    last_expansion: int = 0
    requests: dict[str, dict[str, Any]] = field(default_factory=dict)
    checks: Counter[str] = field(default_factory=Counter)
    expansions: int = 0

    def prompt(self) -> dict[str, str]:
        return {
            "route_id": self.route_id,
            "strategy": self.strategy,
            **({"previous_answer": self.previous_answer} if self.previous_answer else {}),
        }

    def cost(self) -> dict[str, Any]:
        usage = list(self.requests.values())
        input_tokens = _token_total(usage, "input_tokens")
        output_tokens = _token_total(usage, "output_tokens")
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "tokens": input_tokens + output_tokens
            if isinstance(input_tokens, int) and isinstance(output_tokens, int)
            else "unknown",
            "request_ids": list(self.requests),
            "sources": sorted({item["source"] for item in usage}),
            "unknown_request_ids": [
                key for key, item in self.requests.items()
                if not all(isinstance(item[field], int) for field in ("input_tokens", "output_tokens"))
            ],
        }


def _token_total(usage: list[dict[str, Any]], field: str) -> int | str:
    values = [item[field] for item in usage]
    return sum(values) if all(isinstance(value, int) for value in values) else "unknown"


def _actual_tokens(value: object) -> int | str:
    return value if type(value) is int and value >= 0 else "unknown"


class OnlineSearch:
    def __init__(self, mode: OnlineSearchMode, goals: list[dict[str, Any]]) -> None:
        self.mode = mode
        self.routes: list[OnlineRoute] = []
        self.weights = {goal["id"]: goal["weight"] for goal in goals}
        self.selection_counts: Counter[str] = Counter()
        self._request_routes: dict[str, str] = {}
        self._evidence_attributions: dict[str, dict[str, str]] = {}
        self._gain_streak = 0
        self._rotation = 0

    def config(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "max_candidates": _MAX_CANDIDATES,
            "gain_selections_before_exploration": _GAIN_SELECTIONS_BEFORE_EXPLORATION,
        }

    def register_candidates(self, text: str) -> bool:
        if len(text) > _MAX_PROPOSAL_CHARS:
            return False
        try:
            proposal = json.loads(text)
        except (ValueError, RecursionError):
            return False
        candidates = proposal.get("candidates") if isinstance(proposal, dict) else None
        if not isinstance(candidates, list) or not 1 <= len(candidates) <= _MAX_CANDIDATES:
            return False
        strategies = []
        for candidate in candidates:
            strategy = candidate.get("strategy") if isinstance(candidate, dict) else None
            if not isinstance(strategy, str) or not 1 <= len(strategy.strip()) <= _MAX_STRATEGY_CHARS:
                return False
            strategies.append(strategy.strip())
        if len(set(strategy.casefold() for strategy in strategies)) != len(strategies):
            return False
        self.routes = [
            OnlineRoute(f"route_{index:02d}", strategy)
            for index, strategy in enumerate(strategies, start=1)
        ]
        return True

    def candidate_records(self) -> list[dict[str, str]]:
        return [
            {"route_id": route.route_id, "strategy_id": stable_id("strategy", route.strategy)}
            for route in self.routes
        ]

    def select(
        self, request_id: str, supports: dict[str, tuple[ScopedDerivation, ...]],
    ) -> tuple[OnlineRoute, dict[str, Any]]:
        rows = self._route_records(supports)
        eligible_scores = {
            row["route_id"]: Fraction(row["effective_gain"], row["cost"]["tokens"])
            for row in rows if row["gain_ranking_exclusion"] is None
        }
        untried = next((route for route in self.routes if not route.last_expansion), None)
        if untried is not None:
            route, strategy = untried, "cold_start"
        elif self.mode == "round_robin":
            route, strategy = self._rotate(), "round_robin"
        elif self._gain_streak >= _GAIN_SELECTIONS_BEFORE_EXPLORATION:
            route, strategy = min(self.routes, key=lambda item: item.last_expansion), "explore"
            self._gain_streak = 0
        elif eligible_scores:
            ranked = [route for route in self.routes if route.route_id in eligible_scores]
            route, strategy = max(ranked, key=lambda item: eligible_scores[item.route_id]), "gain"
            self._gain_streak += 1
        else:
            route, strategy = self._rotate(), "fallback_round_robin"
        self.selection_counts[strategy] += 1
        return route, {
            "event": "route_selection",
            "decision_id": stable_id("selection", request_id),
            "request_id": request_id,
            "route_id": route.route_id,
            "strategy": strategy,
            **({"reason": "no_comparable_effective_gain"} if strategy == "fallback_round_robin" else {}),
            "routes": rows,
            "frozen_goal_ids": list(self.weights),
            "supported_goal_ids": [goal for goal in self.weights if goal in supports],
        }

    def _rotate(self) -> OnlineRoute:
        route = self.routes[self._rotation]
        self._rotation = (self._rotation + 1) % len(self.routes)
        return route

    def settle(
        self, route: OnlineRoute, request_id: str, expansion: int, reply: ModelReply,
    ) -> None:
        route.last_expansion = expansion
        route.expansions += 1
        self._request_routes[request_id] = route.route_id
        route.requests[request_id] = {
            "input_tokens": _actual_tokens(reply.input_tokens),
            "output_tokens": _actual_tokens(reply.output_tokens),
            "source": reply.usage_source,
        }

    def settle_auxiliary(
        self, route: OnlineRoute, request_records: list[dict[str, Any]],
    ) -> None:
        """Attribute auxiliary requests to the route whose failure admitted them."""
        for record in request_records:
            usage = record["usage"]
            route.requests[record["request_id"]] = {
                "input_tokens": _actual_tokens(usage["input_tokens"]),
                "output_tokens": _actual_tokens(usage["output_tokens"]),
                "source": usage["source"],
            }

    def attribute_evidence(
        self, route: OnlineRoute, evidence_ids: tuple[str, ...], *, attribution: str,
    ) -> None:
        """Credit merged evidence to the parent route that can now use it."""
        for evidence_id in evidence_ids:
            self._evidence_attributions[evidence_id] = {
                "route_id": route.route_id,
                "attribution": attribution,
            }

    def record_verification(
        self, route: OnlineRoute, answer: str, verification: dict[str, Any],
    ) -> dict[str, Any]:
        route.previous_answer = answer
        checks = Counter(check["status"] for check in verification.get("checks", ()))
        route.checks.update(checks)
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "source": "local_independent_verification",
            "applicable": verification["applicable"],
            "checks": dict(checks),
        }

    @property
    def cold_start_complete(self) -> bool:
        return all(route.last_expansion for route in self.routes)

    def summary(
        self, supports: dict[str, tuple[ScopedDerivation, ...]], stop_reason: str,
    ) -> dict[str, Any]:
        return {
            "selection_counts": dict(self.selection_counts),
            "frozen_goal_ids": list(self.weights),
            "supported_goal_ids": [goal for goal in self.weights if goal in supports],
            "routes": self._route_records(supports),
            "untried_routes": [
                {"route_id": route.route_id, "reason": stop_reason}
                for route in self.routes if not route.last_expansion
            ],
        }

    def _route_records(self, supports: dict[str, tuple[ScopedDerivation, ...]]) -> list[dict[str, Any]]:
        credits: dict[str, list[dict[str, Any]]] = {route.route_id: [] for route in self.routes}
        for goal, weight in self.weights.items():
            for support in supports.get(goal, ()):
                # A shared goal contributes once, to the earliest surviving producer.
                explicit = self._evidence_attributions.get(support.evidence_id)
                route_id = explicit["route_id"] if explicit is not None else self._request_routes.get(
                    support.request_id
                )
                if route_id is not None:
                    credits[route_id].append({
                        "goal_id": goal, "weight": weight, "evidence_id": support.evidence_id,
                        "request_id": support.request_id,
                        "attribution": (
                            explicit["attribution"] if explicit is not None else "route_request"
                        ),
                    })
                    break

        records = []
        for route in self.routes:
            credit = credits[route.route_id]
            gain = sum(item["weight"] for item in credit)
            cost = route.cost()
            exclusion = None
            if not route.last_expansion:
                exclusion = "untried"
            elif cost["tokens"] == "unknown":
                exclusion = "unknown_token_cost"
            elif cost["tokens"] == 0:
                exclusion = "zero_token_cost"
            elif not gain:
                exclusion = "no_effective_gain"
            records.append({
                "route_id": route.route_id,
                "last_expansion": route.last_expansion or None,
                "expansions": route.expansions,
                "verification_checks": dict(route.checks),
                "effective_gain": gain,
                "credit": credit,
                "cost": cost,
                "gain_ranking_exclusion": exclusion,
            })
        return records
