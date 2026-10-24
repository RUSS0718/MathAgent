"""Deliberate ALIGN-04 bypass probes; public acceptance must reject each mutation."""

import io
import unittest
from unittest.mock import patch

from tests.test_star_product_protocol_failure import StarProtocolFailureTest


def _run(case_name):
    result = unittest.TextTestRunner(stream=io.StringIO()).run(
        StarProtocolFailureTest(case_name))
    return bool(result.failures or result.errors)


def main():
    probes = [
        ("known protocol failure reclassified as unknown",
         "test_complete_invalid_json_is_a_known_protocol_failure_never_unknown",
         patch("showcase.solver_harness.calls.KNOWN_PROTOCOL_FAILURES", frozenset())),
        ("unrepaired protocol failure left unterminated",
         "test_complete_invalid_json_is_a_known_protocol_failure_never_unknown",
         patch("showcase.solver_harness.controller.protocol_failure_exit", return_value=None),
         patch("showcase.solver_harness.harness.protocol_failure_exit", return_value=None)),
        ("disabled schema gate fakes protocol success",
         "test_streamed_complete_schema_invalid_is_protocol_failure_never_unknown",
         patch("showcase.solver_harness.intern_port.schema_error", lambda *_args, **_kw: None)),
        ("unknown request decision gate bypassed",
         "test_unknown_outcome_keeps_human_gate_and_zero_automatic_resend",
         patch("showcase.star_product_recovery.authorize_resume", return_value=True)),
    ]
    for probe in probes:
        name, case_name, *mutations = probe
        entered = [mutation.__enter__() for mutation in mutations]
        try:
            detected = _run(case_name)
        finally:
            for mutation in reversed(mutations):
                mutation.__exit__(None, None, None)
        if not detected:
            raise AssertionError(f"bypass was not detected by the expected invariant: {name}")
        print(f"{name}: bypass detected by public acceptance failure")


if __name__ == "__main__":
    main()
