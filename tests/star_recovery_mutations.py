"""Deliberate bypass probes; product acceptance must reject each mutation."""

import io
import unittest
from unittest.mock import patch

from tests.mutation_support import require_assertion_failure
from tests.test_star_product_recovery import StarRecoveryTest


def main():
    probes = [
        ("unknown decision guard",
         "test_unknown_requires_explicit_new_identity_and_keeps_original_budget",
         patch("showcase.star_product_recovery.authorize_resume", return_value=True)),
        ("completed action reuse",
         "test_process_exit_after_recorded_verifier_response_reuses_it",
         patch("showcase.solver_harness.calls.dispatch",
               side_effect=lambda h, r, op, req, sessions: sessions(h, r, op, req))),
    ]
    for name, method, mutation in probes:
        with mutation:
            result = unittest.TextTestRunner(stream=io.StringIO()).run(StarRecoveryTest(method))
        require_assertion_failure(result, name)
        print(f"{name}: bypass detected by public acceptance failure")


if __name__ == "__main__":
    main()
