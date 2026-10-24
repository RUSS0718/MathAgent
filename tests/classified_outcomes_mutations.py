"""Deliberate bypass probes; public acceptance must reject each mutation."""

import io
import unittest
from unittest.mock import patch

from tests.test_star_product_classified_outcomes import StarClassifiedOutcomesTest


def _drop_classifications(state, reply, **kwargs):
    """Bypass: record nothing; the review verdict stands alone."""
    return [], []


def _unverified_entries(state, reply, *, step_id, report, review_call_id, suffix,
                        plan_version, attempt_index):
    """Bypass: accept every declaration without receipt or dependency checks."""
    from showcase.solver_harness.classified import CATEGORIES, declarations

    entries, rejections = [], []
    for item in declarations(reply):
        if item.get("category") not in CATEGORIES:
            continue
        entries.append({
            **item,
            "claim_indexes": item.get("claim_indexes", []),
            "receipt_ids": item.get("receipt_ids", []),
            "dependencies": item.get("dependencies", []),
            "result_id": f"{step_id}:outcome-{len(entries) + 1}{suffix}",
            "source": step_id,
            "review_call_id": review_call_id,
            "evidence_level": ("tool_verified" if item["category"] == "Computation"
                               else "llm_reviewed"),
            "proven": item["category"] != "Conjecture",
            "valid": True,
            "invalidated": False,
            "plan_version": plan_version,
            "attempt_index": attempt_index,
        })
    return entries, rejections


def _promoting_entries(state, reply, **kwargs):
    """Bypass: verify normally, then promote Conjectures into proven premises."""
    from showcase.solver_harness.classified import build_entries

    entries, rejections = build_entries(state, reply, **kwargs)
    for entry in entries:
        entry["evidence_level"] = "llm_reviewed"
        entry["proven"] = True
    return entries, rejections


def main():

    import showcase.solver_harness.classified as classified

    probes = [
        ("dropped classifications",
         "test_challenge_retains_proven_lemma_and_leaves_conjecture_unproven",
         patch.object(classified, "build_entries", _drop_classifications)),
        ("unverified receipts and dependencies",
         "test_forged_receipts_and_unsupported_upgrades_are_rejected",
         patch.object(classified, "build_entries", _unverified_entries)),
        ("promoted conjectures",
         "test_challenge_retains_proven_lemma_and_leaves_conjecture_unproven",
         patch.object(classified, "build_entries", _promoting_entries)),
    ]
    for name, method, mutation in probes:
        with mutation:
            result = unittest.TextTestRunner(stream=io.StringIO()).run(
                StarClassifiedOutcomesTest(method))
        if not result.failures and not result.errors:
            raise AssertionError(f"bypass was not detected by the expected invariant: {name}")
        print(f"{name}: bypass detected by public acceptance failure")


if __name__ == "__main__":
    main()
