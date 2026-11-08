"""Controller-accepted, typed evidence and root-obligation progress."""

import json
from collections.abc import Mapping, Sequence
from hashlib import sha256
from typing import Any

from .specification import normalize_problem_spec, validate_evidence_category


def collect_obligation_evidence(
    specification: Any,
    declarations: Any,
    *,
    report: Mapping[str, Any],
    run_id: str,
    review_call_id: str,
    state_revision: int,
    work_unit_id: str,
    work_unit_obligation_ids: Sequence[str],
    plan_version: int,
    attempt_index: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Accept reviewer-labelled evidence only when it references report claims."""
    spec = normalize_problem_spec(specification)
    roots = {item["obligation_id"] for item in spec["root_obligations"]}
    mapped_roots = set(work_unit_obligation_ids)
    claims = report.get("claims", []) if isinstance(report, Mapping) else []
    if not isinstance(declarations, list):
        return [], []
    report_digest = sha256(
        json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    accepted, rejected, seen_obligations = [], [], set()
    for index, declaration in enumerate(declarations):
        if not isinstance(declaration, Mapping):
            rejected.append({"index": index, "reason": "invalid_obligation_evidence"})
            continue
        obligation_id = declaration.get("obligation_id")
        category = declaration.get("evidence_category")
        claim_indexes = declaration.get("claim_indexes", [])
        reason = None
        if obligation_id not in roots:
            reason = "unknown_root_obligation"
        elif obligation_id not in mapped_roots:
            reason = "root_obligation_not_mapped_to_work_unit"
        elif obligation_id in seen_obligations:
            reason = "duplicate_root_obligation_evidence"
        elif not isinstance(review_call_id, str) or not review_call_id:
            reason = "missing_review_source"
        elif (not isinstance(claim_indexes, list) or not claim_indexes or any(
            type(item) is not int or not 0 <= item < len(claims) for item in claim_indexes
        )):
            reason = "invalid_report_source"
        else:
            try:
                validate_evidence_category(spec, obligation_id, category)
            except (TypeError, ValueError):
                reason = "evidence_category_mismatch"
        if reason is not None:
            rejected.append({"index": index, "obligation_id": obligation_id, "reason": reason})
            continue
        accepted.append({
            "evidence_id": f"{work_unit_id}:{review_call_id}:obligation-evidence:{index}",
            "obligation_id": obligation_id,
            "evidence_category": category,
            "claim_indexes": list(claim_indexes),
            "source_report_sha256": report_digest,
            "source": work_unit_id,
            "run_id": run_id,
            "role": "step_verifier",
            "review_call_id": review_call_id,
            "state_revision": state_revision,
            "plan_version": plan_version,
            "attempt_index": attempt_index,
            "specification_version": spec["specification_version"],
            "valid": True,
            "invalidated": False,
        })
        seen_obligations.add(obligation_id)
    return accepted, rejected


def update_obligation_ledger(
    specification: Any,
    ledger: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Project current root coverage; invalidated evidence never keeps a root closed."""
    spec = normalize_problem_spec(specification)
    by_root: dict[str, list[str]] = {item["obligation_id"]: [] for item in spec["root_obligations"]}
    for item in evidence:
        if (isinstance(item, Mapping) and item.get("valid", True)
                and not item.get("invalidated", False)
                and spec["specification_version"]
                in item.get("applicable_specification_versions", [item.get("specification_version")])
                and item.get("obligation_id") in by_root
                and isinstance(item.get("evidence_id"), str)):
            by_root[item["obligation_id"]].append(item["evidence_id"])
    previous = {item.get("obligation_id"): item for item in ledger if isinstance(item, Mapping)}
    return [
        {
            **previous.get(root["obligation_id"], {}),
            "obligation_id": root["obligation_id"],
            "obligation_type": root["obligation_type"],
            "status": "satisfied" if by_root[root["obligation_id"]] else "open",
            "evidence_refs": by_root[root["obligation_id"]],
            "specification_version": spec["specification_version"],
        }
        for root in spec["root_obligations"]
    ]


def all_root_obligations_satisfied(ledger: Sequence[Mapping[str, Any]]) -> bool:
    return bool(ledger) and all(item.get("status") == "satisfied" for item in ledger)
