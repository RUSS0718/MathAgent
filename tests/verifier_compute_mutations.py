"""Deliberate bypass probes; public acceptance must reject each mutation."""

import io
import unittest
from copy import deepcopy
from unittest.mock import patch

from tests.mutation_support import require_assertion_failure
from tests.test_star_product_verifier_compute import StarVerifierComputeTest

FORGED = {
    "receipt_id": "forged-verifier-receipt", "executed": True, "status": "success",
    "exit_code": 0, "output": 2, "assertion_matched": True, "source": "forged",
}


def _skip_execution(harness, run, *, request, role, step_id, round_number, attempt_index, seq,
                    review_call_id):
    """Bypass: answer the reviewer's request without any isolated execution."""
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


def main():
    import showcase.solver_harness.tool_ports as tool_ports

    tool_ports.RegistryToolPort._original_execute = tool_ports.RegistryToolPort.execute
    probes = [
        ("skipped isolated execution", "test_step_verifier_request_executes_and_continues_review",
         patch("showcase.solver_harness.verifier_compute.execute_request",
               side_effect=_skip_execution)),
        ("replaced receipt output", "test_step_verifier_request_executes_and_continues_review",
         patch("showcase.solver_harness.tool_ports.RegistryToolPort.execute",
               side_effect=_replace_receipt)),
    ]
    for name, method, mutation in probes:
        with mutation:
            result = unittest.TextTestRunner(stream=io.StringIO()).run(
                StarVerifierComputeTest(method))
        require_assertion_failure(result, name)
        print(f"{name}: bypass detected by public acceptance failure")


if __name__ == "__main__":
    main()
