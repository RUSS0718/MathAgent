"""Verification of proof-graph ledger and counterexample provenance."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Mapping

from .classified import PROVEN_CATEGORIES, _complete_receipt_ids
from .counterexample import consumed_result


def _clean(value: str) -> str:
    """Normalize the narrow text binding used by the polynomial receipt adapter."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()


def recorded_call(state: Mapping, call_id: object, role: str) -> Mapping | None:
    """Resolve a completed call only when its persisted Run identity and role match."""
    calls = state.get("calls")
    if not isinstance(call_id, str) or not isinstance(calls, Mapping):
        return None
    call = calls.get(call_id)
    if (not isinstance(call, Mapping) or call.get("role") != role
            or call.get("run_id") != state.get("run_id")
            or call.get("problem_hash") != state.get("problem_hash")
            or call.get("config_hash") != state.get("config_hash")):
        return None
    return call


def reasoner_report_call(state: Mapping, step_id: str, report: Mapping,
                         plan_version: int, attempt_index: int,
                         before_revision: int | None = None) -> str | None:
    """Find the completed reasoner call matching the saved report and attempt."""
    claims = [item.get("statement") for item in report.get("claims", [])
              if isinstance(item, Mapping) and isinstance(item.get("statement"), str)]
    candidates = []
    for call_id, call in state.get("calls", {}).items():
        request = call.get("request") if isinstance(call, Mapping) else None
        requested_step = request.get("step") if isinstance(request, Mapping) else None
        response = call.get("response") if isinstance(call, Mapping) else None
        response_claims = [item.get("statement") for item in response.get("claims", [])
                           if isinstance(item, Mapping) and isinstance(item.get("statement"), str)] \
            if isinstance(response, Mapping) and isinstance(response.get("claims"), list) else None
        if (isinstance(call, Mapping) and call.get("role") == "reasoner"
                and call.get("status") in {"completed", "recovered_pending_validation"}
                and call.get("run_id") == state.get("run_id")
                and call.get("problem_hash") == state.get("problem_hash")
                and call.get("config_hash") == state.get("config_hash")
                and call.get("plan_version") == plan_version
                and call.get("attempt_index") == attempt_index
                and (before_revision is None or call.get("request_revision", -1) < before_revision)
                and isinstance(requested_step, Mapping)
                and requested_step.get("step_id") == step_id
                and response_claims == claims):
            candidates.append((call.get("request_revision", -1), call_id))
    return max(candidates, default=(None, None))[1]


def _verify_record(state: Mapping, record: Mapping) -> tuple[dict | None, str | None]:
    expected_version = state.get("specification_version", 0)
    if (record.get("specification_version", 0) != expected_version
            or type(record.get("specification_version", 0)) is not int):
        return None, "cross_version_source"
    if record.get("invalidated") is True or record.get("valid") is not True:
        return None, "source_invalidated"
    if record.get("category") == "Conjecture":
        return None, "conjecture_not_importable"
    if record.get("category") not in PROVEN_CATEGORIES or record.get("proven") is not True:
        return None, "not_verified_proof"
    statement, scope = record.get("statement"), record.get("scope")
    if not isinstance(statement, str) or not statement.strip():
        return None, "missing_statement"
    if not isinstance(scope, str) or not scope.strip():
        return None, "missing_scope"
    if record.get("evidence_level") not in {"llm_reviewed", "tool_verified"}:
        return None, "invalid_evidence_grade"
    expected_grade = "tool_verified" if record.get("category") == "Computation" else "llm_reviewed"
    if record.get("evidence_level") != expected_grade:
        return None, "unsupported_evidence_upgrade"
    result_id, step_id = record.get("result_id"), record.get("source")
    steps = state.get("steps")
    step = steps.get(step_id) if isinstance(step_id, str) and isinstance(steps, Mapping) else None
    if not isinstance(result_id, str) or not result_id or not isinstance(step, Mapping):
        return None, "missing_report_source"
    if type(record.get("plan_version")) is not int or type(record.get("attempt_index")) is not int:
        return None, "missing_attempt_identity"
    call_id = record.get("review_call_id")
    review = recorded_call(state, call_id, "step_verifier")
    if (review is None or review.get("status") != "completed"
            or review.get("plan_version") != record["plan_version"]
            or review.get("attempt_index") != record["attempt_index"]):
        return None, "invalid_review_source"
    review_request, response = review.get("request"), review.get("response")
    if not isinstance(review_request, Mapping) or not isinstance(response, Mapping):
        return None, "review_record_mismatch"
    verification = step.get("verification")
    if (not isinstance(verification, Mapping)
            or response.get("verdict") != verification.get("verdict")):
        return None, "review_record_mismatch"
    if not any(
        isinstance(item, Mapping)
        and item.get("category") == record.get("category")
        and item.get("statement") == statement
        and item.get("scope") == scope
        and item.get("claim_indexes", []) == record.get("claim_indexes", [])
        and item.get("receipt_ids", []) == record.get("receipt_ids", [])
        and item.get("dependencies", []) == record.get("dependencies", [])
        for item in response.get("classified_outcomes", [])
    ):
        return None, "review_did_not_accept_record"
    report = step.get("report")
    report_call_id = reasoner_report_call(
        state, step_id, report, record["plan_version"], record["attempt_index"],
        before_revision=review.get("request_revision", -1),
    ) if isinstance(report, Mapping) else None
    if report_call_id is None:
        return None, "missing_report_call_source"
    indexes, claims = record.get("claim_indexes"), step["report"].get("claims", [])
    if (not isinstance(indexes, list) or not indexes
            or any(type(index) is not int or not 0 <= index < len(claims) for index in indexes)):
        return None, "invalid_report_claim_refs"
    receipts = record.get("receipt_ids", [])
    if not isinstance(receipts, list) or any(not isinstance(item, str) for item in receipts):
        return None, "invalid_receipt_refs"
    if any(item not in _complete_receipt_ids(state) for item in receipts):
        return None, "invalid_receipt_source"
    if record.get("category") == "Computation" and not receipts:
        return None, "missing_required_receipt"
    return {
        "report_call_id": report_call_id,
        "review_call_id": call_id,
        "receipt_ids": sorted(set(receipts)),
    }, None


def importable_ledger_rows(state: Mapping, ledger: list) -> tuple[list, list]:
    """Reject duplicate result identities and return source-checked ledger rows."""
    result_ids = []
    for item in ledger:
        if isinstance(item, Mapping) and isinstance(item.get("result_id"), str):
            result_ids.append(item["result_id"])
    if len(set(result_ids)) != len(result_ids):
        raise ValueError("duplicate_ledger_result_id")
    accepted, rejected = [], []
    for item in ledger:
        if not isinstance(item, Mapping):
            rejected.append({"source_id": "unknown", "reason": "invalid_ledger_row"})
            continue
        if not isinstance(item.get("result_id"), str) or not item["result_id"]:
            rejected.append({"source_id": "unknown", "reason": "missing_result_id"})
            continue
        verified, reason = _verify_record(state, item)
        if verified is None:
            rejected.append({"source_id": item["result_id"], "reason": reason})
        else:
            accepted.append((item, verified))
    return accepted, rejected


def dependency_closure(
    rows: list,
    rejected_ids: set[str] | None = None,
    known_ids: set[str] | None = None,
) -> tuple[list, list]:
    """Order rows after their AND dependencies and retain unmappable descendants."""
    pending = list(rows)
    result_ids = [
        row.get("result_id") for row, _source in pending if isinstance(row, Mapping)
    ]
    if len(result_ids) != len(set(result_ids)):
        raise ValueError("duplicate_ledger_result_id")

    rejected_sources = set(rejected_ids or ())
    historical_sources = set(known_ids or ())
    imported_ids: set[str] = set()
    all_ids = set(result_ids)
    imported = []
    rejected = []
    while pending:
        deferred = []
        progressed = False
        for row, source in pending:
            result_id = row.get("result_id")
            dependencies = row.get("dependencies", [])
            if result_id in rejected_sources:
                progressed = True
            elif (not isinstance(dependencies, list)
                    or any(not isinstance(item, str) for item in dependencies)):
                rejected.append({"source_id": result_id, "reason": "invalid_dependencies"})
                rejected_sources.add(result_id)
                progressed = True
            elif any(item in rejected_sources and item not in historical_sources
                     for item in dependencies):
                rejected.append({"source_id": result_id, "reason": "unmapped_dependency"})
                rejected_sources.add(result_id)
                progressed = True
            elif all(item in imported_ids or item in historical_sources
                     for item in dependencies):
                imported.append((row, source))
                imported_ids.add(result_id)
                progressed = True
            else:
                deferred.append((row, source))
        if progressed:
            pending = deferred
            continue
        for row, _source in deferred:
            result_id = row.get("result_id")
            dependencies = row.get("dependencies", [])
            reason = "cyclic_dependency" if any(
                item in all_ids for item in dependencies
            ) else "unmapped_dependency"
            rejected.append({"source_id": result_id, "reason": reason})
            rejected_sources.add(result_id)
        break
    return imported, rejected


def counterexample_attempts(state: Mapping, proposition_id) -> list[dict]:
    """Read persisted counterexample checks; candidates never become refutations."""
    result = []
    steps = state.get("steps", {})
    calls = state.get("calls", {})
    if not isinstance(steps, Mapping) or not isinstance(calls, Mapping):
        return result
    for step_id, step in steps.items():
        if not isinstance(step, Mapping):
            continue
        checks = step.get("counterexample_checks", {})
        if not isinstance(checks, Mapping):
            continue
        for verifier_id, check in checks.items():
            if not isinstance(check, Mapping) or not isinstance(check.get("target"), Mapping):
                continue
            target = check["target"]
            claim, assumptions = target.get("claim"), target.get("assumptions")
            if (not isinstance(claim, str) or not isinstance(assumptions, list)
                    or not all(isinstance(item, str) for item in assumptions)):
                continue
            call_id = check.get("call_id")
            call = recorded_call(state, call_id, "researcher")
            verifier = recorded_call(state, verifier_id, "step_verifier")
            declared = target
            if (call is None or verifier is None
                    or check.get("verifier_call_id") != verifier_id
                    or call.get("status") != "completed"
                    or call.get("request", {}).get("action") != "counterexample_check"):
                continue
            report = step.get("report")
            reply = verifier.get("response")
            verified_target = None
            if isinstance(report, Mapping) and isinstance(reply, Mapping):
                from .counterexample import target as verified_claim_target

                verified_target = verified_claim_target(report, reply.get("answer_claim"))
            if verified_target != declared:
                continue
            consumed = consumed_result(
                state, step_id=step_id, verifier_call_id=verifier_id, declared=declared
            )
            if consumed is None:
                status = "unknown" if call.get("status") in {"unknown_outcome", "dispatched", "streaming"} else "rejected"
                verdict = None
            else:
                status = ("proposed" if consumed.get("verdict") == "FOUND_COUNTEREXAMPLE"
                          else "rejected")
                verdict = consumed["verdict"]
            scope = "counterexample:" + "|".join(sorted(" ".join(item.split()) for item in assumptions))
            result.append({
                "attempt_id": "attempt_" + hashlib.sha256(
                    f"{state.get('run_id')}:{call_id}:{claim}".encode()).hexdigest()[:32],
                "conclusion": proposition_id(state, claim, scope),
                "scope": scope,
                "claim": claim,
                "assumptions": assumptions,
                "step_id": step_id,
                "claim_index": verified_target.get("claim_index"),
                "counterexample": consumed.get("counterexample") if consumed else None,
                "violated_conclusion": consumed.get("violated_conclusion") if consumed else None,
                "status": status,
                "direction": "counterexample",
                "grade": None,
                "premises": [],
                "source_refs": [f"counterexample:{verifier_id}", f"research:{call_id}"],
                "result_id": None,
                "lineage": None,
                "verdict": verdict,
            })
            result[-1]["id"] = result[-1]["attempt_id"]
    return result


def verified_counterexample_receipt(
    state: Mapping,
    candidate: Mapping,
    receipt_id: object,
    persisted_receipts: Mapping[str, Mapping],
) -> Mapping | None:
    """Accept only an executed, persisted checker receipt bound to this exact claim."""
    if not isinstance(receipt_id, str):
        return None
    receipt = persisted_receipts.get(receipt_id)
    if not isinstance(receipt, Mapping):
        return None
    state_receipts = state.get("tool_receipts")
    if (not isinstance(state_receipts, list)
            or not any(item == receipt for item in state_receipts if isinstance(item, Mapping))
            or receipt_id not in _complete_receipt_ids(state)):
        return None
    expected = {
        "claim": candidate.get("claim"),
        "assumptions": candidate.get("assumptions"),
        "counterexample": candidate.get("counterexample"),
        "violated_conclusion": candidate.get("violated_conclusion"),
    }
    output = receipt.get("output")
    if not (
        receipt.get("run_id") == state.get("run_id")
        and receipt.get("step_id") == candidate.get("step_id")
        and receipt.get("claim_index") == candidate.get("claim_index")
        and receipt.get("executed") is True
        and receipt.get("status") == "success"
        and receipt.get("unknown_outcome") is not True
        and receipt.get("source") in {"local_precheck", "docker_isolated"}
        and receipt.get("tool") in {"polynomial_check", "python_math"}
        and receipt.get("output_available") is True
        and isinstance(receipt.get("input"), Mapping)
        and isinstance(output, Mapping)
    ):
        return None
    if receipt.get("tool") == "polynomial_check":
        arguments = receipt["input"]
        from ..polynomial import PolynomialChecker

        try:
            checked_output = PolynomialChecker().check(arguments)
        except (TypeError, ValueError):
            return None
        coefficients = arguments.get("coefficients")
        candidates = arguments.get("candidates")
        variable = arguments.get("variable")
        domain = arguments.get("domain")
        if (arguments.get("schema_version") != 1 or not isinstance(variable, str)
                or not isinstance(coefficients, list) or not coefficients
                or not all(isinstance(item, str) for item in coefficients)
                or not isinstance(candidates, list) or len(candidates) != 1
                or candidates[0] != expected["counterexample"]
                or domain != {"kind": "real"}
                or expected["assumptions"] != [f"{variable} is real"]):
            return None
        compact_coefficients = ",".join(coefficients)
        claim = f"{variable}={candidates[0]} is a root of polynomial coefficients {compact_coefficients}"
        contradiction = (
            f"{variable}={candidates[0]} is not a root of polynomial coefficients "
            f"{compact_coefficients}"
        )
        checked = next((item for item in output.get("candidates", [])
                        if isinstance(item, Mapping)
                        and item.get("candidate") == candidates[0]), None)
        return receipt if (
            output == checked_output
            and output.get("checker") == "polynomial_check"
            and output.get("checker_version") == "polynomial-check-v1"
            and output.get("candidate_status") == "conflict"
            and isinstance(checked, Mapping)
            and checked.get("status") == "conflict"
            and checked.get("in_domain") is True
            and checked.get("duplicate") is False
            and checked.get("residual") not in {None, "0"}
            and _clean(expected["claim"]) == claim
            and _clean(expected["violated_conclusion"]) == contradiction
        ) else None
    return receipt if (
        receipt.get("input") == expected
        and output.get("verdict") == "FOUND_COUNTEREXAMPLE"
        and output.get("claim") == expected["claim"]
        and output.get("assumptions") == expected["assumptions"]
        and output.get("counterexample") == expected["counterexample"]
        and output.get("violated_conclusion") == expected["violated_conclusion"]
        and isinstance(output.get("checker_version"), str)
        and bool(output["checker_version"])
    ) else None
