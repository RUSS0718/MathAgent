"""Focused zero-paid E3 gate; skips and crashed probes never count as PASS."""

import unittest

from tests.rb06_mutations import main as mutations

CASES = [
    "tests.test_star_rb06_recovery",
    "tests.test_star_rb06_faults",
    "tests.test_mutation_support",
    "tests.test_star_rb02_computation",
    "tests.test_star_rb03_obligations",
    "tests.test_star_product_semantics",
    "tests.test_star_transport_policy",
    "tests.test_star_product_control",
    "tests.test_star_product_budget",
    "tests.test_star_product_python",
    "tests.test_star_product_streaming_recovery.StarStreamingRecoveryTest."
    "test_process_exit_mid_stream_keeps_unknown_and_requires_explicit_new_identity",
    "tests.test_star_product_align_recovery.StarAlignChainRecoveryTest."
    "test_chain_resume_crosses_every_new_persistent_boundary",
    "tests.test_star_product_align_recovery.StarAlignChainRecoveryTest."
    "test_exhausted_shared_budget_stops_resumed_continuation_before_dispatch",
    "tests.test_star_product_align_recovery.StarAlignChainRecoveryTest."
    "test_expired_original_deadline_refuses_resumed_compute_continuation",
    "tests.test_star_product_align_recovery.StarAlignHistoryCompatibilityTest",
    "tests.test_star_product_classified_outcomes.StarClassifiedOutcomesTest."
    "test_damaged_receipts_and_absent_review_source_are_rejected",
    "tests.test_star_product_classified_outcomes.StarClassifiedOutcomesTest."
    "test_forged_receipts_and_unsupported_upgrades_are_rejected",
    "tests.test_star_product_final_binding.StarFinalBindingTest."
    "test_delivery_rewrite_cannot_inherit_whole_review",
    "tests.test_star_acceptance.DeliveredReviewTest."
    "test_early_reject_and_multiple_candidates_select_actual_delivery",
    "tests.test_python_executor_docker.DockerExecutorTest."
    "test_container_restrictions_have_actual_failure_examples",
    "tests.test_python_executor_docker.DockerExecutorTest.test_timeout_kills_container_with_descendant",
    "tests.test_python_executor_docker.DockerExecutorTest.test_cancellation_kills_a_sleeping_container",
]


def main():
    suite = unittest.defaultTestLoader.loadTestsFromNames(CASES)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful() or result.skipped or result.expectedFailures:
        raise SystemExit("E3 incomplete: failure, skip or expected failure")
    mutations()
    print(f"E3 PASS: {result.testsRun} tests, 5 targeted bypasses; paid provider requests=0")


if __name__ == "__main__":
    main()
