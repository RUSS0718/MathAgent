"""Verifier-classified outcomes: controller verification and the ledger.

The reviewer — never the Reasoner's own report — decides what a review
establishes. A reply may declare classified outcomes (Lemma, Conjecture,
Computation, Definition, Answer) under any step verdict. The controller
verifies each declaration against the reviewed report, real executed tool
receipts and already-established dependencies before atomically appending the
authoritative ledger; forged references, unsupported upgrades and unknown,
stale or cyclic dependencies are rejected individually and never promoted.
"""

from collections.abc import Mapping

from .computation_evidence import has_computation_output
from .counterexample import missing_direction, target

CATEGORIES = ("Lemma", "Conjecture", "Computation", "Definition", "Answer")
CONJECTURE = "Conjecture"
PROVEN_CATEGORIES = ("Lemma", "Computation", "Definition", "Answer")


def declarations(reply):
    """The reviewer's explicitly classified outcomes; absent means none."""
    if not isinstance(reply, Mapping):
        return []
    value = reply.get("classified_outcomes")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _real_receipt_ids(state):
    """Receipt IDs of actually executed, successful computations in this Run."""
    return {
        receipt.get("receipt_id")
        for receipt in state.get("tool_receipts", [])
        if isinstance(receipt, Mapping)
        and receipt.get("executed") is True
        and receipt.get("status") == "success"
        and has_computation_output(receipt)
        and isinstance(receipt.get("receipt_id"), str)
    }


def _complete_receipt_ids(state):
    """Executed successes whose receipt still carries its integrity references.

    A receipt ID alone is a claim; the references make it auditable. A receipt
    that was executed but lost every reference and its input payload is a
    damaged receipt and cannot back a classified outcome.
    """
    return {
        receipt.get("receipt_id")
        for receipt in state.get("tool_receipts", [])
        if isinstance(receipt, Mapping)
        and receipt.get("executed") is True
        and receipt.get("status") == "success"
        and isinstance(receipt.get("receipt_id"), str)
        and receipt.get("unknown_outcome") is not True
        and (
            receipt.get("input") is not None
            or any(
                isinstance(receipt.get(key), str) and receipt[key]
                for key in ("code_ref", "stdout_ref", "stderr_ref", "receipt_ref")
            )
        )
    }


def _review_call_exists(state, review_call_id):
    """Whether the ruling's stated review source is acceptable.

    A run that records calls must be able to point at the review call; a state
    without any recorded calls (pure ledger unit under test) has nothing to
    check against and keeps the previous behaviour.
    """
    if not isinstance(review_call_id, str) or not review_call_id:
        return False
    calls = state.get("calls")
    if not isinstance(calls, Mapping) or not calls:
        return True
    call = calls.get(review_call_id)
    return isinstance(call, Mapping) and call.get("role") in {
        "step_verifier", "whole_solution_verifier"}


def _established_ids(state):
    """Accepted step IDs and result IDs of valid proven records."""
    ids = {
        step_id
        for step_id, step in state.get("steps", {}).items()
        if isinstance(step, Mapping)
        and isinstance(step.get("verification"), Mapping)
        and step["verification"].get("valid") is True
        and step["verification"].get("verdict") == "ACCEPT"
    }
    records = [*state.get("accepted_results", []), *state.get("verified_results_ledger", [])]
    for record in records:
        if (
            isinstance(record, Mapping)
            and isinstance(record.get("result_id"), str)
            and not record.get("invalidated")
            and record.get("valid", True)
            and record.get("status") not in {"INVALIDATED", "invalidated"}
            and record.get("category") != CONJECTURE
        ):
            ids.add(record["result_id"])
    return ids


def build_entries(state, reply, *, step_id, report, review_call_id, suffix,
                  plan_version, attempt_index):
    """Verify declared classifications and build authoritative ledger entries.

    Returns ``(entries, rejections)``. Entries carry a controller-assigned
    result identity, the reviewed report source, the controller-recorded
    review source and only real executed receipts; rejections record why a
    declaration was refused and never reach the ledger.
    """
    claims = report.get("claims", []) if isinstance(report, Mapping) else []
    receipts = _real_receipt_ids(state)
    complete = _complete_receipt_ids(state)
    known = _established_ids(state)
    review_recorded = _review_call_exists(state, review_call_id)
    declared = target(report, reply.get("answer_claim")) if isinstance(reply, Mapping) else None
    entries, rejections = [], []
    for index, item in enumerate(declarations(reply)):
        category = item.get("category")
        statement = item.get("statement")
        scope = item.get("scope")
        result_id = f"{step_id}:outcome-{len(entries) + 1}{suffix}"
        reason = None
        if not review_recorded:
            reason = "unknown_review_source"
        elif category not in CATEGORIES:
            reason = "unknown_category"
        elif not isinstance(statement, str) or not statement.strip():
            reason = "missing_statement"
        elif not isinstance(scope, str) or not scope.strip():
            reason = "missing_scope"
        indexes = item.get("claim_indexes", [])
        if reason is None and (
            not isinstance(indexes, list)
            or any(type(value) is not int or not 0 <= value < len(claims) for value in indexes)
        ):
            reason = "invalid_report_source"
        if (reason is None and declared and missing_direction(declared)
                and category in PROVEN_CATEGORIES
                and (not indexes or declared["claim_index"] in indexes
                     or statement == declared["claim"])):
            reason = "missing_proof_direction"
        refs = item.get("receipt_ids", [])
        if reason is None and (
            not isinstance(refs, list)
            or any(not isinstance(value, str) for value in refs)
            or any(value not in receipts for value in refs)
        ):
            reason = "unverified_tool_receipt"
        elif reason is None and any(value not in complete for value in refs):
            reason = "damaged_tool_receipt"
        elif reason is None and category == "Computation" and not refs:
            reason = "unsupported_computation"
        dependencies = item.get("dependencies", [])
        if reason is None and (
            not isinstance(dependencies, list)
            or any(not isinstance(value, str) for value in dependencies)
        ):
            reason = "unknown_dependency"
        if reason is None:
            for value in dependencies:
                if value == result_id:
                    reason = "cyclic_dependency"
                elif value not in known:
                    reason = "unknown_dependency"
                if reason:
                    break
        if reason is not None:
            rejections.append({
                "index": index,
                "category": category if isinstance(category, str) else None,
                "reason": reason,
            })
            continue
        entry = {
            "result_id": result_id,
            "category": category,
            "statement": statement,
            "scope": scope,
            "source": step_id,
            "claim_indexes": list(indexes),
            "review_call_id": review_call_id,
            "receipt_ids": list(refs),
            "dependencies": list(dependencies),
            "evidence_level": (
                "conjecture" if category == CONJECTURE
                else "tool_verified" if category == "Computation" else "llm_reviewed"
            ),
            "proven": category in PROVEN_CATEGORIES,
            "valid": True,
            "invalidated": False,
            "plan_version": plan_version,
            "attempt_index": attempt_index,
        }
        entries.append(entry)
        known.add(result_id)
    return entries, rejections


def outcome_counts(entries):
    """Category counts for the review event; insertion order preserved."""
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["category"]] = counts.get(entry["category"], 0) + 1
    return counts
