"""Deliberate bypass probes for final proof delivery; public acceptance must reject each."""

import io
import unittest
from unittest.mock import patch

from tests.mutation_support import require_assertion_failure
from tests.test_star_product_final_binding import StarFinalBindingTest
from tests.test_star_product_final_proof import StarFinalProofTest


def _empty_proof_basis(state):
    """Bypass: deliver conclusion statements only; no proof bodies travel."""
    return []


def _archived_proof_basis(state):
    """Bypass: leak archived (traced-back) derivations into the delivered basis."""
    from showcase.solver_harness.finalize import proof_basis

    proofs = proof_basis(state)
    for failure in state.get("failure_records", []):
        for step_id, record in (failure.get("archived_steps") or {}).items():
            report = record.get("report", {}) if isinstance(record, dict) else {}
            proofs.append({
                "step_id": step_id,
                "argument": report.get("argument", ""),
                "claims": [],
                "tool_receipts": [],
                "review": {"verdict": record.get("verification", {}).get("verdict", "ACCEPT")},
                "artifact": __import__(
                    "showcase.final_evidence", fromlist=["artifact_identity"]
                ).artifact_identity(report.get("argument", "")),
            })
    return proofs


def _unbound_delivery(run, answer):
    """Bypass: accept any delivery text regardless of the whole-review binding."""
    from showcase.final_evidence import bind_verification

    return True, bind_verification(answer, {
        "status": "unknown", "checker": "whole_solution_verifier",
        "checker_version": "star-whole-review-v1", "scope": "whole_solution_llm_review",
        "findings": ["llm_whole_review_accepted"],
        "limitations": ["LLM review does not prove mathematical correctness or completeness."],
    })


def main():
    probes = [
        ("dropped proof delivery",
         StarFinalProofTest("test_valid_proof_bodies_reach_final_generation_and_whole_review"),
         patch("showcase.solver_harness.finalize.proof_basis", _empty_proof_basis)),
        ("archived derivation resurrection",
         StarFinalProofTest("test_valid_proof_bodies_reach_final_generation_and_whole_review"),
         patch("showcase.solver_harness.finalize.proof_basis", _archived_proof_basis)),
        ("S4 text binding bypass",
         StarFinalBindingTest("test_delivery_rewrite_cannot_inherit_whole_review"),
         patch("showcase.star_product_pipeline.delivery_verification", _unbound_delivery)),
    ]
    for name, case, mutation in probes:
        with mutation:
            result = unittest.TextTestRunner(stream=io.StringIO()).run(case)
        require_assertion_failure(result, name)
        print(f"{name}: bypass detected by public acceptance failure")


if __name__ == "__main__":
    main()
