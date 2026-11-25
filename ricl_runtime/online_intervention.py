"""Bounded same-checkpoint intervention for the normal solve loop."""

import hashlib
import json
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from itertools import combinations
from typing import TYPE_CHECKING, Any

from .derivations import DerivationChange, DerivationScope, ScopedDerivation, ScopedDerivationGraph
from .identity import stable_id
from .math_verification import MathVerification
from .reasoning_state import SharedReasoningState

if TYPE_CHECKING:
    from .runtime import _ModelAttempt

EvidenceRecheck = Callable[[tuple[ScopedDerivation, ...]], Iterable[str]]
Revocation = tuple[ScopedDerivation, DerivationChange]
_INTERVENTION_REQUESTS = 4  # Diagnosis, two single-step arms, and a parent continuation.
_INTERVENTION_VERIFICATIONS = 3  # One independent check per arm and one parent merge recheck.
_INTERVENTION_TOOL_CALLS = 3  # One tool opportunity per arm and one for the parent continuation.


def recheck_derivations(
    graph: ScopedDerivationGraph, scope: DerivationScope, recheck: EvidenceRecheck | None,
) -> tuple[Revocation, ...]:
    """Revoke independently invalidated evidence and retain its pre-revocation provenance."""
    if recheck is None:
        return ()
    active = {support.evidence_id: support for support in graph.active()}
    revoked = []
    for evidence_id in recheck(tuple(active.values())):
        if evidence_id in active and (change := graph.revoke(evidence_id, scope=scope)) is not None:
            revoked.append((active[evidence_id], change))
    return tuple(revoked)


@dataclass(frozen=True)
class _CriticalFailure:
    evidence: tuple[dict[str, Any], ...]
    targets: dict[str, str]
    dependencies: tuple[ScopedDerivation, ...]

    @property
    def ids(self) -> list[str]:
        return [item["evidence_id"] for item in self.evidence]


def _critical_failure(
    verifier: MathVerification,
    graph: ScopedDerivationGraph,
    scope: DerivationScope,
    checks: list[dict[str, Any]],
    revocations: tuple[Revocation, ...],
) -> _CriticalFailure:
    """Select failures that affect a frozen goal and collect their currently usable dependencies."""
    goals = {goal.id: goal.kind for goal in verifier.goals}
    supported = graph.goal_supports(scope)
    failed = {check["kind"]: check for check in checks if check["status"] == "failed"}
    targets = {
        goal_id: kind for goal_id, kind in goals.items() if goal_id not in supported and kind in failed
    }
    evidence = [failed[kind] for kind in targets.values()]
    dependency_kinds = {kind for check in evidence for kind in check["premise_kinds"]}
    premise_ids: set[str] = set()
    for support, change in revocations:
        if not change.reopened_goal_ids:
            continue
        targets.update((goal_id, goals[goal_id]) for goal_id in change.reopened_goal_ids)
        evidence.append({
            "evidence_id": support.evidence_id,
            "status": "revoked",
            "reason": "necessary_support_lost",
            "derivation": support.public(),
            "claim": support.check["evidence"],
            **change.public(),
        })
        premise_ids.update(support.premise_ids)
    dependencies = []
    available = graph.applicable(scope)
    while True:
        related = [
            support for support in available
            if support.proposition_id in premise_ids or support.kind in dependency_kinds
        ]
        if len(related) == len(dependencies):
            return _CriticalFailure(tuple(evidence), targets, tuple(related))
        dependencies = related
        premise_ids.update(premise for support in related for premise in support.premise_ids)


@dataclass(frozen=True)
class _Arm:
    attempt: "_ModelAttempt"
    verification: dict[str, Any]
    added: tuple[ScopedDerivation, ...]
    new_goals: dict[str, ScopedDerivation]
    failed_goals: frozenset[str]
    retained: bool
    comparable: bool


@dataclass(frozen=True)
class InterventionContinuation:
    checkpoint_id: str
    merged_evidence_ids: tuple[str, ...] = ()
    failure_status: str | None = None
    parent_route_id: str | None = None

    def request_metadata(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "merged_evidence_ids": list(self.merged_evidence_ids),
        }


class OnlineIntervention:
    """Admit at most one pair per Run, using the caller's root request and tool ledger."""

    def __init__(
        self,
        verifier: MathVerification,
        trace: list[dict[str, Any]],
        recheck: EvidenceRecheck | None,
        *,
        account_verification: Callable[[float], None] | None = None,
        budget_reserve: Callable[[], str | None] | None = None,
        budget_stop: Callable[[], str | None] | None = None,
        budget_overrun: Callable[[], str | None] | None = None,
    ) -> None:
        self._verifier = verifier
        self._trace = trace
        self._recheck = recheck
        self._account_verification = account_verification or (lambda _: None)
        self._budget_reserve = budget_reserve or (lambda: None)
        self._budget_stop = budget_stop or (lambda: None)
        self._budget_overrun = budget_overrun or (lambda: None)
        self._started = False

    def consider(
        self,
        *,
        request_id: str,
        build_prompt: Callable[[], str],
        checks: list[dict[str, Any]],
        revocations: tuple[Revocation, ...],
        state: SharedReasoningState,
        scope: DerivationScope,
        remaining_requests: int,
        remaining_tools: int,
        max_output_tokens: int | str,
        route_id: str | None = None,
        decision_id: str | None = None,
        dispatch: Callable[[str, dict[str, Any]], "_ModelAttempt"],
        execute_tools: Callable[["_ModelAttempt", SharedReasoningState, int], tuple[int, str | None]],
    ) -> InterventionContinuation | None:
        """Try a pair on a critical independently established failure with continuation reserved."""
        graph = state.derivations
        failure = _critical_failure(self._verifier, graph, scope, checks, revocations)
        reserve_reason = self._budget_reserve() if failure.targets and not self._started else None
        reason = (
            "no_critical_failure" if not failure.targets else
            "already_triggered" if self._started else
            "insufficient_model_requests" if remaining_requests < _INTERVENTION_REQUESTS else
            "insufficient_full_budget" if reserve_reason is not None else
            "admitted"
        )
        self._trace.append({
            "event": "counterfactual_trigger_evaluated",
            "request_id": request_id,
            "eligible": bool(failure.targets),
            "reason": reason,
            "failure_evidence_ids": failure.ids,
            "affected_goal_ids": list(failure.targets),
            "remaining_model_requests": remaining_requests,
            "required_model_requests": _INTERVENTION_REQUESTS,
            "remaining_tool_calls": remaining_tools,
            "required_tool_calls": _INTERVENTION_TOOL_CALLS,
            "required_local_verifications": _INTERVENTION_VERIFICATIONS
            if reason == "admitted" else "unknown",
            "budget_reserve_reason": reserve_reason,
        })
        if reason != "admitted":
            if reserve_reason is not None:
                self._trace.append({
                    "event": "counterfactual_budget_blocked",
                    "request_id": request_id,
                    "stage": "admission",
                    "reason": reserve_reason,
                    "failure_evidence_ids": failure.ids,
                })
            return None
        self._started = True
        frozen = state.fork()
        evidence_ids = tuple(support.evidence_id for support in graph.applicable(scope))
        checkpoint_supports = frozenset(support.evidence_id for support in graph.active())
        shared_evidence_ids = [item.evidence_id for item in frozen.valid_evidence()]
        checkpoint_id = stable_id("checkpoint", {
            "request_id": request_id, "scope": scope.public(),
            "checks": evidence_ids, "shared_evidence": shared_evidence_ids,
            "failure_evidence_ids": failure.ids,
        })
        context = {
            "checkpoint_id": checkpoint_id,
            "trigger_request_id": request_id,
            "failure_evidence_ids": failure.ids,
            **({"route_id": route_id} if route_id is not None else {}),
            **({"decision_id": decision_id} if decision_id is not None else {}),
        }
        delivery = {
            "delivered_check_evidence_ids": list(evidence_ids),
            "referenced_evidence_ids": shared_evidence_ids,
        }
        dependency_ids = [support.evidence_id for support in failure.dependencies]
        budget = {
            "model_requests": 1,
            "local_verifications": 1,
            "tool_calls": min(1, max(0, (remaining_tools - 1) // 2)),
            "max_output_tokens": max_output_tokens,
        }
        self._trace.append({
            "event": "counterfactual_started", **context,
            "checkpoint_evidence_ids": list(evidence_ids),
            "shared_evidence_ids": shared_evidence_ids,
            "dependency_evidence_ids": dependency_ids,
            "reserved_model_requests": _INTERVENTION_REQUESTS,
            "reserved_local_verifications": _INTERVENTION_VERIFICATIONS,
            "arm_budget": budget,
        })

        def conclude(
            reason: str, *, merged: tuple[ScopedDerivation, ...] = (), failure_status: str | None = None,
            **fields: Any,
        ) -> InterventionContinuation:
            identifiers = tuple(support.evidence_id for support in merged)
            self._trace.append({
                "event": "counterfactual_merge", **context, **fields,
                "status": "merged" if merged else "withheld",
                "reason": reason, "merged_evidence_ids": list(identifiers),
            })
            return InterventionContinuation(
                checkpoint_id,
                identifiers,
                failure_status,
                parent_route_id=route_id,
            )

        def admit(stage: str) -> InterventionContinuation | None:
            reason = self._budget_stop()
            if reason is None:
                return None
            self._trace.append({
                "event": "counterfactual_budget_blocked",
                **context,
                "stage": stage,
                "reason": reason,
            })
            return conclude(f"budget_{stage}_{reason}", failure_status=reason)

        # Use exactly the same problem, checkpoint claims and failure report on both arms.
        prompt = build_prompt()
        failure_report = _json({
            "failed_evidence": failure.evidence,
            "affected_goal_ids": list(failure.targets),
            "related_dependencies": [support.check for support in failure.dependencies],
        })
        local_context = f"Independently checked failure and its related dependencies:\n{failure_report}"
        if (budget_block := admit("diagnosis")) is not None:
            return budget_block
        diagnostic = dispatch(
            prompt + "\n\n" + local_context
            + '\n\nFor this local failure, return only JSON with two short strings, '
              '"hypothesis" and "strategy". Propose one targeted repair, citing the failure and dependencies.',
            {"request_kind": "counterfactual_diagnosis", **context, **delivery},
        )

        if diagnostic.failure_status is not None:
            return conclude("diagnosis_" + diagnostic.failure_status, failure_status=diagnostic.failure_status)
        diagnosis = _read_diagnosis(diagnostic.reply.text)
        if diagnosis is None:
            self._trace.append({
                "event": "counterfactual_diagnosis", **context,
                "request_id": diagnostic.request_id, "status": "invalid",
            })
            return conclude("diagnosis_invalid")
        hypothesis, strategy = diagnosis
        diagnosis_id = stable_id("diagnosis", {**context, "hypothesis_sha256": _digest(hypothesis)})
        strategy_id = stable_id("strategy", {"diagnosis_id": diagnosis_id, "strategy_sha256": _digest(strategy)})
        self._trace.append({
            "event": "counterfactual_diagnosis", **context, "status": "proposed",
            "request_id": diagnostic.request_id, "dependency_evidence_ids": dependency_ids,
            "diagnosis_id": diagnosis_id, "hypothesis_sha256": _digest(hypothesis),
            "strategy_id": strategy_id, "strategy_sha256": _digest(strategy),
        })
        arm_prompt = (
            prompt + "\n\n" + local_context
            + "\n\nSubmit only one bounded repair increment. Preserve the already verified claims."
            + "\n\n" + self._verifier.instructions(scoped_derivations=True)
        )
        arms = {}
        for name in ("control", "treatment"):
            if (budget_block := admit(f"arm_{name}")) is not None:
                return budget_block
            treatment = name == "treatment"
            metadata = {
                **context, "arm": name,
                **({"strategy_id": strategy_id} if treatment else {}),
            }
            attempt = dispatch(
                arm_prompt + ("\n\nTargeted strategy:\n" + strategy if treatment else ""),
                {"request_kind": "counterfactual_arm", **metadata, **delivery},
            )
            if attempt.failure_status is not None:
                self._trace.append({
                    "event": "counterfactual_arm_checked", **metadata,
                    "request_id": attempt.request_id, "budget": budget,
                    "status": attempt.failure_status,
                })
                return conclude("arm_" + attempt.failure_status, failure_status=attempt.failure_status)
            branch = frozen.fork()
            verification_started = time.perf_counter()
            arm = self._verify_arm(
                attempt, branch.derivations, scope, failure, evidence_ids, checkpoint_supports,
            )
            self._account_verification(
                round((time.perf_counter() - verification_started) * 1000, 3)
            )
            if (reason := self._budget_overrun()) is not None:
                self._trace.append({
                    "event": "counterfactual_budget_blocked",
                    **context,
                    "stage": f"arm_{name}_tools",
                    "reason": reason,
                })
                return conclude(f"budget_arm_{name}_tools_{reason}", failure_status=reason)
            used_tools, tool_failure = execute_tools(attempt, branch, budget["tool_calls"])
            arms[name] = arm
            self._trace.append({
                "event": "counterfactual_arm_checked", **metadata, "request_id": attempt.request_id,
                "status": tool_failure or ("checked" if arm.comparable else "unknown"),
                "budget": budget,
                "used": {"model_requests": 1, "local_verifications": 1, "tool_calls": used_tools},
                "actual_model": attempt.reply.model, "elapsed_ms": attempt.elapsed_ms,
                "usage": {"input_tokens": attempt.reply.input_tokens,
                          "output_tokens": attempt.reply.output_tokens, "source": attempt.reply.usage_source},
                "retained_checkpoint_evidence": arm.retained,
                "new_goal_ids": list(arm.new_goals),
                "failed_goal_ids": sorted(arm.failed_goals),
                "resolved_goal_ids": [goal for goal in arm.new_goals if goal in failure.targets],
                "new_evidence_ids": [support.evidence_id for support in arm.added],
                "used_evidence_ids": arm.verification["references"]["used_evidence_ids"],
            })
            if tool_failure is not None:
                return conclude("arm_" + tool_failure, failure_status=tool_failure)
            if (reason := self._budget_overrun()) is not None:
                self._trace.append({
                    "event": "counterfactual_budget_blocked",
                    **context,
                    "stage": f"arm_{name}_completion",
                    "reason": reason,
                })
                return conclude(f"budget_arm_{name}_completion_{reason}", failure_status=reason)

        control, treatment = arms["control"], arms["treatment"]
        comparison = {f"{name}_request_id": arm.attempt.request_id for name, arm in arms.items()}
        if control.attempt.reply.model != treatment.attempt.reply.model:
            return conclude("actual_model_mismatch", **comparison)
        if not (control.retained and treatment.retained):
            return conclude("checkpoint_evidence_not_retained", **comparison)
        if not (control.comparable and treatment.comparable):
            return conclude("independent_comparison_unknown", **comparison)
        wanted, benefit = self._winning_delta(graph, scope, control, treatment)
        if not wanted:
            return conclude(benefit, **comparison)
        verification_started = time.perf_counter()
        merged = self._recheck_merge(
            graph, scope, treatment, wanted, checkpoint_supports,
        )
        self._account_verification(
            round((time.perf_counter() - verification_started) * 1000, 3)
        )
        if not merged:
            return conclude("parent_recheck_failed", **comparison)
        return conclude(benefit, merged=merged, **comparison)

    def _verify_arm(
        self, attempt: "_ModelAttempt", graph: ScopedDerivationGraph, scope: DerivationScope,
        failure: _CriticalFailure, evidence_ids: tuple[str, ...], checkpoint_supports: frozenset[str],
    ) -> _Arm:
        prior = graph.goal_supports(scope)
        _, verification = self._verifier.assess(attempt.reply.text, delivered_evidence_ids=evidence_ids)
        checks = verification["checks"]
        added = self._verifier.record_derivations(graph, checks, request_id=attempt.request_id, scope=scope)
        recheck_derivations(graph, scope, self._recheck)
        active = {support.evidence_id for support in graph.applicable(scope)}
        supported = graph.goal_supports(scope)
        return _Arm(
            attempt, verification, tuple(support for support in added if support.evidence_id in active),
            {goal: supports[0] for goal, supports in supported.items() if goal not in prior},
            frozenset(goal for goal, kind in failure.targets.items() if goal not in supported
                      and any(check["kind"] == kind and check["status"] == "failed" for check in checks)),
            {support.evidence_id for support in graph.active()}.issuperset(checkpoint_supports),
            verification["structure"] == "valid" and bool(checks)
            and all(check["status"] != "unknown" for check in checks),
        )

    def _winning_delta(
        self, parent: ScopedDerivationGraph, scope: DerivationScope, control: _Arm, treatment: _Arm,
    ) -> tuple[tuple[ScopedDerivation, ...], str]:
        """Select the smallest verified difference that establishes an advantage."""
        available = {support.proposition_id for support in parent.applicable(scope)}
        added = {support.proposition_id: support for support in treatment.added}

        def with_premises(goals: Iterable[ScopedDerivation]) -> tuple[ScopedDerivation, ...]:
            pending = list(goals)
            needed = {support.proposition_id for support in pending}
            for support in pending:
                for premise in set(support.premise_ids) - available - needed:
                    pending.append(added[premise])
                    needed.add(premise)
            return tuple(support for support in treatment.added if support.proposition_id in needed)

        def delta_key(delta: tuple[ScopedDerivation, ...]) -> tuple[int, tuple[str, ...]]:
            return len(delta), tuple(support.evidence_id for support in delta)

        repaired = treatment.new_goals.keys() & control.failed_goals
        if repaired:
            return min(
                (with_premises((treatment.new_goals[goal],)) for goal in repaired),
                key=delta_key,
            ), "independently_resolved_failure"
        weights = {goal.id: goal.weight for goal in self._verifier.goals}
        control_gain = sum(weights[goal] for goal in control.new_goals)
        treatment_gain = sum(weights[goal] for goal in treatment.new_goals)
        if treatment_gain <= control_gain:
            return (), "tied" if treatment_gain == control_gain else "control_advantage"
        # The verifier freezes the small goal set and bounds claims per increment.
        options = (
            with_premises(treatment.new_goals[goal] for goal in subset)
            for size in range(1, len(treatment.new_goals) + 1)
            for subset in combinations(treatment.new_goals, size)
            if sum(weights[goal] for goal in subset) > control_gain
        )
        return min(options, key=delta_key), "greater_verified_progress"

    def _recheck_merge(
        self, parent: ScopedDerivationGraph, scope: DerivationScope, treatment: _Arm,
        wanted: tuple[ScopedDerivation, ...], checkpoint_ids: frozenset[str],
    ) -> tuple[ScopedDerivation, ...]:
        """Replay the selected proofs and newly required premises against the parent scope."""
        if not {support.evidence_id for support in parent.active()}.issuperset(checkpoint_ids):
            return ()
        needed = {support.kind for support in wanted}
        _, verification = self._verifier.assess(treatment.attempt.reply.text)
        checks = [check for check in verification["checks"] if check["kind"] in needed]
        fork = parent.fork()
        replayed = self._verifier.record_derivations(
            fork, checks, request_id=treatment.attempt.request_id, scope=scope,
        )
        recheck_derivations(fork, scope, self._recheck)
        required = checkpoint_ids.union(support.evidence_id for support in replayed)
        if not {support.evidence_id for support in fork.active()}.issuperset(required):
            return ()
        if {support.evidence_id for support in replayed} != {support.evidence_id for support in wanted}:
            return ()
        merged = self._verifier.record_derivations(
            parent, checks, request_id=treatment.attempt.request_id, scope=scope,
        )
        self._trace.extend({"event": "derivation_added", **support.public()} for support in merged)
        return merged


def _read_diagnosis(text: str) -> tuple[str, str] | None:
    if len(text) > 4_096:
        return None
    try:
        fields = json.loads(text)
    except (ValueError, RecursionError):
        return None
    if not isinstance(fields, dict) or set(fields) != {"hypothesis", "strategy"}:
        return None
    hypothesis, strategy = fields["hypothesis"], fields["strategy"]
    if all(isinstance(value, str) and 0 < len(value.strip()) <= 1_024 for value in (hypothesis, strategy)):
        try:
            return (hypothesis.strip().encode().decode(), strategy.strip().encode().decode())
        except UnicodeError:
            return None
    return None


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
