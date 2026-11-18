"""Read-only qualification of a persisted formal receipt against its requested scope."""

import hashlib
from collections.abc import Mapping

from .experiment_manifest import canonical_json
from .formal_specification import normalize_target, public_target


def assess_formal_requirement(policy, formal, problem_spec=None):
    """Require object identity, coverage and a current audited receipt together."""
    policy = policy if isinstance(policy, Mapping) else {}
    requirement = policy.get("requirement") or {}
    scope = requirement.get("scope", "original_problem")
    minimum = requirement.get("minimum_grade", "L3" if scope == "original_problem" else "L2")
    result = {"status": "unmet" if policy.get("require_formal") else "default",
              "reason": "formal_receipt_unavailable", "scope": scope,
              "required_grade": minimum, "covered_obligation_ids": []}
    if not isinstance(formal, Mapping):
        return result
    current = formal.get("current")
    if (formal.get("status") != "solved" or not isinstance(current, Mapping)
            or current.get("status") != "solved"
            or current.get("attempt_id") != formal.get("current_attempt_id")
            or current.get("grade") != formal.get("grade")):
        return result
    try:
        target = public_target(normalize_target(policy.get("target")))
    except (TypeError, ValueError):
        return {**result, "reason": "formal_target_unbound"}
    proof = current.get("proof_artifact") or {}
    records = current.get("specifications") or {}
    original = records.get("original_to_spec") or {}
    correspondence = records.get("spec_to_target") or {}
    environment = records.get("target_to_environment") or {}
    valid = (proof.get("accepted") is True and proof.get("kernel_exit") == 0
             and proof.get("cleanup_verified") is True
             and proof.get("target_hash") == target["hash"]
             and correspondence.get("target_hash") == target["hash"]
             and environment.get("target_hash") == target["hash"]
             and environment.get("environment_hash") == proof.get("environment_hash")
             and bool(proof.get("environment_hash")))
    if not valid:
        return {**result, "reason": "formal_source_invalid"}
    rank = {"L2": 2, "L3": 3}
    if minimum not in rank or rank.get(formal.get("grade"), 0) < rank[minimum]:
        return {**result, "reason": "formal_grade_insufficient"}
    if scope == "original_problem":
        if (formal.get("grade") != "L3" or any(
                records.get(key, {}).get("review_status") != "reviewed"
                for key in ("original_to_spec", "spec_to_target", "target_to_environment"))):
            return {**result, "reason": "original_correspondence_unreviewed"}
        if not isinstance(problem_spec, Mapping):
            return {**result, "reason": "problem_spec_unbound"}
        spec_hash = hashlib.sha256(canonical_json(problem_spec)).hexdigest()
        if original.get("problem_spec_hash") != spec_hash:
            return {**result, "reason": "problem_spec_changed"}
        roots = problem_spec.get("root_obligations", [])
        if not roots or original.get("root_obligations") != roots:
            return {**result, "reason": "formal_coverage_incomplete"}
        result["covered_obligation_ids"] = [root["obligation_id"] for root in roots]
    elif scope == "formal_target":
        if requirement.get("target_hash") != target["hash"]:
            return {**result, "reason": "requested_target_mismatch"}
    else:
        return {**result, "reason": "formal_scope_unsupported"}
    return {**result, "status": "met" if policy.get("require_formal") else "default",
            "reason": "scope_verified"}
