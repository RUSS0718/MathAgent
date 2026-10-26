"""E3 minimal bypasses must hit their named public behavior assertion."""

import time
from copy import deepcopy
from unittest.mock import patch

from showcase import request_transport, star_acceptance
from showcase.solver_harness import tool_precheck
from tests.final_proof_mutations import _unbound_delivery
from tests.mutation_support import require_assertion_failure, run_case
from tests.test_star_acceptance import DeliveredReviewTest
from tests.test_star_product_final_binding import StarFinalBindingTest
from tests.test_star_rb02_computation import ComputationJobTest
from tests.test_star_rb06_faults import RobustFaultTest

evaluate = star_acceptance._evaluate_delivery
execute = tool_precheck._execute
events = request_transport.response_events


def first_review(job, run, contexts):
    """Bypass actual delivery provenance with the first same-role review."""
    changed = deepcopy(run)
    changed["state"]["whole_solution_reviews"] = run["state"]["whole_solution_reviews"][:1]
    return evaluate(job, changed, contexts)


def promote_uncompared(*args, **kwargs):
    """Bypass comparison provenance: successful execution becomes a match."""
    run, receipt = execute(*args, **kwargs)
    if receipt["status"] == "success":
        receipt.update(comparison_status="matched", assertion_matched=True)
    return run, receipt


def ignore_deadline(url, **kwargs):
    """Bypass only the transport supervisor's absolute deadline."""
    kwargs["deadline"] = time.monotonic() + 5
    yield from events(url, **kwargs)


def main():
    probes = [
        ("delivery provenance", DeliveredReviewTest(
            "test_early_reject_and_multiple_candidates_select_actual_delivery"),
         patch.object(star_acceptance, "_evaluate_delivery", first_review), "'review_bound': False"),
        ("comparison classification", ComputationJobTest(
            "test_output_without_expected_continues_review_without_meta"),
         patch.object(tool_precheck, "_execute", promote_uncompared), "True is not false"),
        ("applicable obligation", RobustFaultTest(
            "test_sharp_obligation_still_challenges_after_numeric_computation"),
         patch("showcase.solver_harness.counterexample.missing_direction", return_value=False),
         "RB06 applicable obligation"),
        ("absolute deadline", RobustFaultTest(
            "test_public_http_deadline_stops_waiting_and_only_late_usage_can_settle"),
         patch.object(request_transport, "response_events", ignore_deadline), "RB06 hard deadline"),
        ("S4 text binding", StarFinalBindingTest(
            "test_delivery_rewrite_cannot_inherit_whole_review"),
         patch("showcase.star_product_pipeline.delivery_verification", _unbound_delivery),
         "'failed' != 'succeeded'"),
    ]
    for name, case, mutation, expected in probes:
        with mutation:
            result = run_case(case)
        count = require_assertion_failure(result, name, expected_assertion=expected)
        print(f"{name}: detected by {count} target assertion failure(s); errors=0; skipped=0")
        for _, traceback in result.failures:
            print(next(line for line in traceback.splitlines() if line.startswith("AssertionError:")))


if __name__ == "__main__":
    main()
