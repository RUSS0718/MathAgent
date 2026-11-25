"""Independent checks for bounded, public mathematical claims."""

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from fractions import Fraction
from math import isqrt
from typing import Any

from .derivations import DerivationScope, ScopedDerivation, ScopedDerivationGraph
from .identity import stable_id

_MAX_CHECKS = 8
_MAX_REPLY_CHARS = 16_384
_UNSIGNED_RATIONAL = r"[0-9]{1,12}(?:/[1-9][0-9]{0,11})?"
_RATIONAL = rf"[+-]?{_UNSIGNED_RATIONAL}"
_AFFINE = rf"(?:({_UNSIGNED_RATIONAL})\s*\*?\s*)?x\s*(?:([+-])\s*({_UNSIGNED_RATIONAL}))?"
_RADICAL_PROBLEM = re.compile(
    rf"\s*(?:solve\s+)?(?:√|sqrt)\s*\(\s*{_AFFINE}\s*\)\s*=\s*{_AFFINE}\s*[.!?]?\s*",
    re.I,
)
_SOLUTION_ANSWER = re.compile(
    rf"(?:final answer:\s*)?(?:(?:the complete solution set is|solution set:)\s*)?"
    rf"(?:x\s*=\s*({_RATIONAL})|\{{([^{{}}]*)\}})\s*[.!]?",
    re.I,
)


@dataclass(frozen=True)
class VerificationGoal:
    id: str
    kind: str
    weight: int = 1


@dataclass(frozen=True)
class ScopedCheck:
    status: str
    scope: str
    reason: str
    evidence: dict[str, object] = field(default_factory=dict)
    premises: tuple[str, ...] = ()
    direction: str | None = None
    satisfies_goal: bool = False
    solutions: tuple[str, ...] | None = None
    premise_kinds: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()


@dataclass(frozen=True)
class MathVerification:
    """A frozen plan whose check functions are independent of the solve loop."""

    name: str
    goals: tuple[VerificationGoal, ...]
    claim_shapes: tuple[str, ...]
    check_claim: Callable[[str, dict[str, Any]], ScopedCheck]

    def instructions(self, *, scoped_derivations: bool = False) -> str:
        return (
            'Return one JSON object with "answer" (free text) and "checks" (up to 8 public claims). '
            'For solution-set binding, end the answer with "Solution set: {…}" listing exact '
            "rational roots, or {} for an empty set. Choose your own derivation and omit checks "
            "it does not support. Supported check shapes:\n" + "\n".join(self.claim_shapes)
            + (
                '\nIf you used previously verified evidence, report its IDs in "used_evidence_ids".'
                if scoped_derivations else ""
            )
        )

    def public_goals(self) -> list[dict[str, object]]:
        return [asdict(goal) for goal in self.goals]

    def assess(
        self, text: str, *, prior_checks: Sequence[dict[str, Any]] = (),
        delivered_evidence_ids: tuple[str, ...] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        answer, claims, structure, reported_ids = _read_increment(text)
        checks = []
        for goal in self.goals:
            matching = [claim for claim in claims if claim.get("kind") == goal.kind]
            if not matching:
                continue
            if len(matching) == 1:
                verdict = self.check_claim(goal.kind, matching[0])
            else:
                verdict = ScopedCheck("unknown", goal.kind, "ambiguous_duplicate_claims")
            check = {
                "kind": goal.kind,
                "status": verdict.status,
                "scope": verdict.scope,
                "reason": verdict.reason,
                "premises": list(verdict.premises),
                "direction": verdict.direction,
                "evidence": verdict.evidence,
                "goal_id": goal.id if verdict.satisfies_goal else None,
            }
            if verdict.status == "verified":
                check["derivation"] = {
                    "scope": DerivationScope(assumptions=frozenset(verdict.assumptions)).public(),
                    "premise_kinds": list(verdict.premise_kinds),
                }
                check["evidence_id"] = stable_id(
                    "evidence", {"criterion_goal": goal.id, "check": check},
                )
            elif verdict.status == "failed":
                check["premise_kinds"] = list(verdict.premise_kinds)
                check["evidence_id"] = stable_id(
                    "failure-evidence", {"criterion_goal": goal.id, "check": check},
                )
            if verdict.solutions is not None:
                check["solutions"] = list(verdict.solutions)
            checks.append(check)

        submitted_kinds = {check["kind"] for check in checks}
        reused_checks = [
            check for check in prior_checks
            if check["goal_id"] is not None and check["kind"] not in submitted_kinds
        ]
        verification = {
            "applicable": True,
            "scope": "complete solution set over the reals",
            "goals": self.public_goals(),
            "checks": checks,
            **({"supporting_checks": reused_checks} if reused_checks else {}),
            "structure": structure,
            "review": {"status": "unknown", "reason": "no_independent_model_review"},
        }
        if delivered_evidence_ids is not None:
            used = [identifier for identifier in delivered_evidence_ids if identifier in (reported_ids or ())]
            verification["references"] = {
                "status": "reported" if used or reported_ids == () else "unknown",
                "used_evidence_ids": used,
            }
        self._bind_answer(answer, verification, (*reused_checks, *checks))
        return answer, verification

    def record_derivations(
        self,
        graph: ScopedDerivationGraph,
        checks: Sequence[dict[str, Any]],
        *,
        request_id: str,
        scope: DerivationScope,
    ) -> tuple[ScopedDerivation, ...]:
        """Turn verified submitted claims into derivations when all premises are available."""
        goals = {goal.kind: goal.id for goal in self.goals}
        added = []
        for check in checks:
            if check["status"] != "verified":
                continue
            metadata = check["derivation"]
            if scope.domain != metadata["scope"]["domain"]:
                continue
            check_scope = DerivationScope(
                metadata["scope"]["domain"], scope.assumptions.union(metadata["scope"]["assumptions"]),
            )
            premises = {support.kind: support.proposition_id for support in graph.applicable(check_scope)}
            required = metadata["premise_kinds"]
            if not all(kind in premises for kind in required):
                continue
            support = graph.add(
                check, criterion_goal_id=goals[check["kind"]], scope=check_scope,
                premise_ids=tuple(premises[kind] for kind in required),
                method=check["reason"], request_id=request_id,
            )
            if support is not None:
                added.append(support)
        return tuple(added)

    def bind_derivations(
        self,
        answer: str,
        verification: dict[str, Any],
        supports: dict[str, tuple[ScopedDerivation, ...]],
        *,
        request_id: str,
    ) -> None:
        """Bind the answer only to applicable surviving supports."""
        selected = {goal: items[0] for goal, items in supports.items()}
        verification.pop("supporting_checks", None)
        reused = [support.check for support in selected.values() if support.request_id != request_id]
        if reused:
            verification["supporting_checks"] = reused
        self._bind_answer(answer, verification, [support.check for support in selected.values()])

    def _bind_answer(
        self, answer: str, verification: dict[str, Any], checks: Sequence[dict[str, Any]],
    ) -> None:
        support = {check["goal_id"]: check for check in checks if check["goal_id"]}
        complete = all(goal.id in support for goal in self.goals)
        solutions = next((check["solutions"] for check in support.values() if "solutions" in check), [])
        answer_set = _answer_set(answer) if complete else None
        if not complete:
            binding_status, binding_reason = "unknown", "missing_verified_solution_set"
        elif answer_set is None:
            binding_status, binding_reason = "unknown", "answer_has_no_unambiguous_solution_set"
        elif answer_set == {Fraction(value) for value in solutions}:
            binding_status, binding_reason = "verified", "answer_matches_verified_solution_set"
        else:
            binding_status, binding_reason = "failed", "answer_differs_from_verified_solution_set"
        verification.update({
            "status": binding_status,
            "reason": binding_reason,
            "completeness": (
                {"status": "verified", "solutions": solutions,
                 "evidence_ids": [support[goal.id]["evidence_id"] for goal in self.goals]}
                if complete else {"status": "unknown", "reason": "missing_verified_goals"}
            ),
        })

    @staticmethod
    def support_rank(verification: dict[str, Any]) -> tuple[bool, bool, int, int]:
        """Prefer bound answers and retain prior support when a later reply weakens it."""
        checks = [*verification.get("checks", ()), *verification.get("supporting_checks", ())]
        return (
            verification.get("status") == "verified",
            verification.get("status") != "failed",
            sum(check["goal_id"] is not None for check in checks),
            sum(check["status"] == "verified" for check in checks),
        )


def _read_increment(text: str) -> tuple[str, list[dict[str, Any]], str, tuple[str, ...] | None]:
    """Accept public claims only from the bounded reply envelope."""
    candidate = text.strip()
    if not candidate.startswith("{"):
        return text, [], "absent", None
    if len(candidate) > _MAX_REPLY_CHARS:
        return "", [], "invalid", None
    try:
        payload = json.loads(candidate)
        answer = payload.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            return "", [], "invalid", None
        answer.encode("utf-8")
    except (ValueError, RecursionError):
        return "", [], "invalid", None
    claims = payload.get("checks")
    if not isinstance(claims, list) or len(claims) > _MAX_CHECKS or any(
        not isinstance(claim, dict) or not isinstance(claim.get("kind"), str) for claim in claims
    ):
        return answer, [], "invalid", None
    raw_ids = payload.get("used_evidence_ids")
    reported_ids = (
        tuple(raw_ids) if isinstance(raw_ids, list) and all(isinstance(item, str) for item in raw_ids)
        else None
    )
    return answer, claims, "valid", reported_ids


def _rational(value: object) -> Fraction | None:
    if isinstance(value, str) and re.fullmatch(_RATIONAL, value):
        return Fraction(value)
    return None


def _rationals(values: object, *, limit: int) -> tuple[Fraction, ...] | None:
    if not isinstance(values, list) or len(values) > limit:
        return None
    rationals = []
    for value in values:
        parsed = _rational(value)
        if parsed is None:
            return None
        rationals.append(parsed)
    return tuple(rationals)


def _answer_set(answer: str) -> set[Fraction] | None:
    lines = [line.strip() for line in answer.splitlines() if line.strip()]
    match = _SOLUTION_ANSWER.fullmatch(lines[-1]) if lines else None
    if match is None:
        return None
    if match[1] is not None:
        return {Fraction(match[1])}
    values = match[2].split(",") if match[2].strip() else []
    rationals = _rationals([value.strip() for value in values], limit=2)
    return set(rationals) if rationals is not None else None


@dataclass(frozen=True)
class _RadicalEquation:
    radicand_slope: Fraction
    radicand_offset: Fraction
    rhs_slope: Fraction
    rhs_offset: Fraction

    @property
    def squared_coefficients(self) -> tuple[Fraction, Fraction, Fraction]:
        return (
            self.rhs_slope ** 2,
            2 * self.rhs_slope * self.rhs_offset - self.radicand_slope,
            self.rhs_offset ** 2 - self.radicand_offset,
        )

    @property
    def rhs_bound(self) -> Fraction:
        return -self.rhs_offset / self.rhs_slope

    def contains(self, value: Fraction) -> bool:
        radicand = self.radicand_slope * value + self.radicand_offset
        rhs = self.rhs_slope * value + self.rhs_offset
        return rhs >= 0 and radicand >= 0 and rhs ** 2 == radicand


def _rational_quadratic_candidates(
    coefficients: tuple[Fraction, Fraction, Fraction],
) -> set[Fraction] | None:
    quadratic, linear, constant = coefficients
    discriminant = linear ** 2 - 4 * quadratic * constant
    if discriminant < 0:
        return set()
    numerator = isqrt(discriminant.numerator)
    denominator = isqrt(discriminant.denominator)
    if numerator ** 2 != discriminant.numerator or denominator ** 2 != discriminant.denominator:
        return None
    root = Fraction(numerator, denominator)
    return {(-linear - root) / (2 * quadratic), (-linear + root) / (2 * quadratic)}


def _check_radical(equation: _RadicalEquation, kind: str, claim: dict[str, Any]) -> ScopedCheck:
    if kind == "necessary_conditions":
        scope = "real radical input and nonnegative right-hand side"
        radicand = _rational(claim.get("radicand_lower_bound"))
        rhs = _rational(claim.get("rhs_lower_bound"))
        if radicand is None or rhs is None:
            return ScopedCheck("unknown", scope, "missing_or_unsupported_bound")
        if (radicand, rhs) != (-equation.radicand_offset / equation.radicand_slope, equation.rhs_bound):
            return ScopedCheck(
                "failed", scope, "incorrect_necessary_conditions",
                {"radicand_lower_bound": str(radicand), "rhs_lower_bound": str(rhs)},
            )
        return ScopedCheck(
            "verified", scope, "real_principal_square_root_conditions",
            {"radicand_lower_bound": str(radicand), "rhs_lower_bound": str(rhs),
             "lower_bound": str(max(radicand, rhs))},
            satisfies_goal=True,
        )

    squared = equation.squared_coefficients
    if kind == "candidate_constraint":
        scope = "quadratic candidate constraint derived by squaring"
        coefficients = _rationals(claim.get("coefficients"), limit=3)
        direction = claim.get("direction")
        if coefficients is None or len(coefficients) != 3 or direction not in ("forward", "equivalent"):
            return ScopedCheck("unknown", scope, "unsupported_constraint")
        scale = coefficients[0] / squared[0]
        if not scale or coefficients != tuple(value * scale for value in squared):
            return ScopedCheck(
                "failed", scope, "incorrect_squared_constraint",
                {"coefficients": [str(value) for value in coefficients]}, direction=direction,
                premise_kinds=("necessary_conditions",) if direction == "equivalent" else (),
            )
        if direction == "equivalent" and claim.get("rhs_nonnegative") is not True:
            return ScopedCheck("unknown", scope, "missing_equivalence_premise", direction=direction)
        premises = (
            (f"x >= {equation.rhs_bound}",) if direction == "equivalent" else ("original equation holds",)
        )
        return ScopedCheck(
            "verified", scope, "exact_squared_constraint",
            {"coefficients": [str(value / squared[0]) for value in squared]},
            premises=premises, direction=direction, satisfies_goal=True,
            premise_kinds=("necessary_conditions",) if direction == "equivalent" else (),
            assumptions=premises if direction == "equivalent" else (),
        )

    candidates = _rational_quadratic_candidates(squared)
    if kind == "candidate_coverage":
        scope = "all real roots of the squared constraint"
        proposed = _rationals(claim.get("candidates"), limit=2)
        if proposed is None:
            return ScopedCheck("unknown", scope, "unsupported_candidate_set")
        method = "exact_quadratic_discriminant"
        if "factor_constants" in claim:
            constants = _rationals(claim["factor_constants"], limit=2)
            if constants is None or len(constants) != 2:
                return ScopedCheck("unknown", scope, "unsupported_factorization")
            first, second = constants
            if (first + second, first * second) != (squared[1] / squared[0], squared[2] / squared[0]):
                return ScopedCheck(
                    "failed", scope, "incorrect_factorization",
                    {"factor_constants": [str(value) for value in constants]},
                    premise_kinds=("candidate_constraint",),
                )
            candidates = {-first, -second}
            method = "exact_quadratic_factorization"
        if candidates is None:
            return ScopedCheck("unknown", scope, "unsupported_candidate_set")
        if set(proposed) != candidates:
            return ScopedCheck(
                "failed", scope, "candidate_set_incorrect_or_incomplete",
                {"candidates": [str(value) for value in sorted(set(proposed))]},
                premise_kinds=("candidate_constraint",),
            )
        return ScopedCheck(
            "verified", scope, method,
            {"candidates": [str(candidate) for candidate in sorted(candidates)]},
            premises=("squared candidate constraint",), satisfies_goal=True,
            premise_kinds=("candidate_constraint",),
        )

    scope = "substitution into the original real equation"
    accepted = _rationals(claim.get("accepted"), limit=2)
    rejected = _rationals(claim.get("rejected"), limit=2)
    if accepted is None or rejected is None:
        return ScopedCheck("unknown", scope, "unsupported_substitution_values")

    if not all(map(equation.contains, accepted)) or any(map(equation.contains, rejected)):
        return ScopedCheck(
            "failed", scope, "incorrect_substitution_classification",
            {"accepted": [str(value) for value in accepted], "rejected": [str(value) for value in rejected]},
            premise_kinds=("necessary_conditions", "candidate_coverage"),
        )
    complete = candidates is not None and set((*accepted, *rejected)) == candidates
    if not complete and not accepted and not rejected:
        return ScopedCheck("unknown", scope, "no_values_checked")
    solutions = tuple(str(value) for value in sorted(set(accepted)))
    return ScopedCheck(
        "verified", scope, "all_candidates_checked" if complete else "listed_values_checked",
        {"accepted": list(solutions), "rejected": [str(value) for value in sorted(set(rejected))]},
        premises=("principal square root in the real domain",), satisfies_goal=complete,
        solutions=solutions if complete else None,
        premise_kinds=("necessary_conditions", "candidate_coverage") if complete else (),
    )


def prepare_math_verification(problem: str) -> MathVerification | None:
    """Freeze route-independent goals for problems covered by an exact criterion."""
    match = _RADICAL_PROBLEM.fullmatch(problem.replace("−", "-"))
    if match is None:
        return None
    a, radicand_sign, b, c, rhs_sign, d = match.groups()
    equation = _RadicalEquation(
        Fraction(a or "1"),
        Fraction(radicand_sign + b) if b is not None else Fraction(0),
        Fraction(c or "1"),
        Fraction(rhs_sign + d) if d is not None else Fraction(0),
    )
    if not equation.radicand_slope or not equation.rhs_slope:
        return None
    name = "real_radical_equation_v1"
    shapes = {
        "necessary_conditions": "radicand_lower_bound, rhs_lower_bound (rational strings)",
        "candidate_constraint": "coefficients (three rational strings, descending powers), "
                                "direction (forward, or equivalent with rhs_nonnegative: true)",
        "candidate_coverage": "candidates (rational strings), and optionally factor_constants "
                              "(two rational strings a, b for (x+a)(x+b))",
        "original_equation_filter": "accepted, rejected (lists of rational strings)",
    }
    return MathVerification(
        name,
        tuple(
            VerificationGoal(stable_id("goal", {"criterion": name, "problem": problem, "kind": kind}), kind)
            for kind in shapes
        ),
        tuple(f'{{"kind": "{kind}", ...}}: {shape}' for kind, shape in shapes.items()),
        lambda kind, claim: _check_radical(equation, kind, claim),
    )
