"""Deliberate bypass probes; public acceptance must reject each mutation."""

import io
import unittest
from copy import deepcopy
from unittest.mock import patch

from tests.test_star_product_explore_compute import StarExploreComputeTest

FORGED = {
    "receipt_id": "forged-explore-receipt", "executed": True, "status": "success",
    "exit_code": 0, "output": 2, "assertion_matched": True, "source": "forged",
}


def _skip_execution(harness, run, *, request, role, step_id, round_number, attempt_index, seq,
                    review_call_id, receipt_prefix="verifier-tool"):
    """Bypass: answer the explorer's request without any isolated execution."""
    from showcase.solver_harness.verifier_compute import request_digest

    receipt = {
        **deepcopy(FORGED), "request_index": seq, "request_digest": request_digest(request),
        "source_role": role, "step_id": step_id, "review_round": round_number,
        "attempt_index": attempt_index, "review_call_id": review_call_id,
        "input": deepcopy(dict(request["arguments"])),
    }
    return run, receipt


def _replace_receipt(self, request):
    """Bypass: execute but swap the executor result before it becomes a receipt."""
    from showcase.solver_harness.tool_ports import RegistryToolPort

    result = RegistryToolPort._original_execute(self, request)
    return {**result, "output": 999, "status": "success", "exit_code": 0}


def _drop_adoption(harness, state, **_kwargs):
    """Bypass: never adopt the computed output into the exploration finding."""
    return []


def main():
    import showcase.solver_harness.tool_ports as tool_ports

    tool_ports.RegistryToolPort._original_execute = tool_ports.RegistryToolPort.execute
    probes = [
        ("skipped isolated execution",
         "test_explore_request_executes_and_continues_exploration",
         patch("showcase.solver_harness.verifier_compute.execute_request",
               side_effect=_skip_execution)),
        ("replaced receipt output",
         "test_explore_request_executes_and_continues_exploration",
         patch("showcase.solver_harness.tool_ports.RegistryToolPort.execute",
               side_effect=_replace_receipt)),
        ("exploration finding without adopted computation",
         "test_explore_counterexample_computation_reaches_planner_request",
         patch("showcase.solver_harness.verifier_compute.verifier_receipts",
               side_effect=_drop_adoption)),
    ]
    for name, method, mutation in probes:
        with mutation:
            result = unittest.TextTestRunner(stream=io.StringIO()).run(
                StarExploreComputeTest(method))
        if not result.failures and not result.errors:
            raise AssertionError(f"bypass was not detected by the expected invariant: {name}")
        print(f"{name}: bypass detected by public acceptance failure")


if __name__ == "__main__":
    main()
