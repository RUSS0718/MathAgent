"""Deterministic correspondence checking for one fixed rational identity template."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

CHECKER_VERSION = "s09-correspondence-v1"
REVIEWER_TYPE = "independent_service"
FIELDS = ("domain", "variables", "quantifiers", "assumptions", "direction", "conclusion")
_FIXED = re.compile(
    r"^For every rational (?P<variable>[A-Za-z_][A-Za-z0-9_']{0,31}), "
    r"(?P<lhs>.+) = (?P<rhs>.+)\.$"
)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _result(
    *, problem: str, problem_spec: Any, target: Any, attempt_id: Any,
    environment_hash: Any, reason: str | None, fields: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    supplied = fields or {}
    confirmed = reason is None and set(supplied) == set(FIELDS) and all(
        supplied.get(name) is True for name in FIELDS
    )
    evidence = {
        "checker_version": CHECKER_VERSION,
        "original_problem_hash": hashlib.sha256(problem.encode("utf-8")).hexdigest()
        if isinstance(problem, str) else None,
        "problem_spec_hash": _sha(problem_spec) if isinstance(problem_spec, Mapping) else None,
        "target_hash": target.get("hash") if isinstance(target, Mapping) else None,
        "attempt_id": attempt_id,
        "environment_hash": environment_hash,
    }
    return {
        "schema_version": 1,
        "status": "confirmed" if confirmed else "not_reviewed",
        "reviewer_type": REVIEWER_TYPE if confirmed else None,
        "reason": reason,
        "field_results": {name: supplied.get(name) is True for name in FIELDS},
        "evidence": evidence,
    }


def check_correspondence(
    problem: str,
    specification: Mapping[str, Any],
    target: Mapping[str, Any],
    attempt_id: str,
    environment_hash: str,
) -> dict[str, Any]:
    """Check actual normalized ProblemSpec/target mappings; never sign or approve."""
    def rejected(reason: str) -> dict[str, Any]:
        return _result(
            problem=problem, problem_spec=specification, target=target,
            attempt_id=attempt_id, environment_hash=environment_hash, reason=reason,
        )
    if not isinstance(attempt_id, str) or not attempt_id.strip():
        return rejected("attempt_id_invalid")
    if not isinstance(environment_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", environment_hash):
        return rejected("environment_hash_invalid")
    if not isinstance(problem, str):
        return rejected("problem_text_invalid")
    if not isinstance(specification, Mapping) or not isinstance(target, Mapping):
        return rejected("correspondence_input_invalid")
    normalized_spec = dict(specification)
    supplied_hash = normalized_spec.pop("hash", None)
    if supplied_hash is not None and (
        not isinstance(supplied_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", supplied_hash)
        or supplied_hash != _sha(normalized_spec)
    ):
        return rejected("problem_spec_hash_invalid")
    if normalized_spec.get("original_problem") != problem:
        return rejected("original_problem_binding_mismatch")
    if set(normalized_spec) != {
        "specification_version", "original_problem", "domain", "quantifiers",
        "assumptions", "directions", "output_requirements", "root_obligations",
        "auxiliary_goals",
    }:
        return rejected("problem_spec_fields_invalid")
    if set(target) != {
        "domain", "variables", "lhs", "rhs", "quantifiers", "assumptions",
        "direction", "hash",
    }:
        return rejected("target_fields_invalid")
    match = _FIXED.fullmatch(problem)
    if match is None:
        return rejected("fixed_template_not_matched")
    variable, lhs, rhs = match.group("variable"), match.group("lhs"), match.group("rhs")
    expected_conclusion = f"{lhs} = {rhs}"
    expected = {
        "domain": "rationals", "variables": [variable],
        "quantifiers": [f"forall {variable}"], "assumptions": [], "direction": "equality",
    }
    roots = normalized_spec.get("root_obligations")
    root = roots[0] if isinstance(roots, list) and len(roots) == 1 and isinstance(roots[0], Mapping) else None
    fields = {
        "domain": target.get("domain") == expected["domain"] and normalized_spec.get("domain") == expected["domain"],
        "variables": target.get("variables") == expected["variables"],
        "quantifiers": target.get("quantifiers") == expected["quantifiers"] and normalized_spec.get("quantifiers") == expected["quantifiers"],
        "assumptions": target.get("assumptions") == [] and normalized_spec.get("assumptions") == [],
        "direction": target.get("direction") == "equality" and normalized_spec.get("directions") == ["equality"],
        "conclusion": (
            target.get("lhs") == lhs and target.get("rhs") == rhs
            and root is not None and root.get("obligation_type") == "universal"
            and root.get("statement") == expected_conclusion
            and root.get("direction") in {None, "equality"}
            and root.get("prerequisite_ids", []) == []
            and normalized_spec.get("output_requirements") == []
            and normalized_spec.get("auxiliary_goals") == []
        ),
    }
    expected_target_hash = _sha({key: target.get(key) for key in (
        "domain", "variables", "lhs", "rhs", "quantifiers", "assumptions", "direction"
    )})
    if target.get("hash") != expected_target_hash:
        return rejected("target_hash_mismatch")
    if not all(fields.values()):
        return rejected(next(name + "_mismatch" for name in FIELDS if not fields[name]))
    return _result(problem=problem, problem_spec=specification, target=target,
                   attempt_id=attempt_id, environment_hash=environment_hash,
                   reason=None, fields=fields)


class IndependentSpecificationReviewer:
    """Restrict signing authority to complete, independently recomputed mappings."""

    def __init__(self, authority):
        self._authority = authority

    def review(self, request, artifact):
        """Issue a review only after checking the original problem and all roots."""
        from .formal_artifact import attempt_hash

        audit = check_correspondence(
            request["problem"]["text"], request["specification"], request["target"],
            request["attempt_id"], artifact.environment_hash,
        )
        if audit["status"] != "confirmed":
            return None, audit
        record = self._authority.issue({
            "review_id": "correspondence-" + request["attempt_id"],
            "reviewer_authority_id": CHECKER_VERSION, "reviewer_type": REVIEWER_TYPE,
            "approved": True, "field_results": audit["field_results"],
            "problem_hash": request["problem"]["hash"],
            "spec_hash": request["specifications"]["original_to_spec"]["problem_spec_hash"],
            "target_hash": request["target"]["hash"],
            "environment_hash": artifact.environment_hash, "attempt_hash": attempt_hash(request),
        }).to_dict()
        return record, audit

    def verify(self, record):
        """Verify a prior review without exposing a general signing operation."""
        return self._authority.verify(record)


__all__ = ["CHECKER_VERSION", "FIELDS", "REVIEWER_TYPE", "check_correspondence",
           "IndependentSpecificationReviewer"]
