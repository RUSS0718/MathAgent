"""Shared verdict for bypass-sensitivity probes.

A mutation probe only proves something when the injected bypass makes the
public acceptance test FAIL AN ASSERTION. A probe whose patched callable
crashes (TypeError, KeyError, ...) proves nothing: the injected code never
reached the invariant under test, so counting it as "bypass detected" would
turn any probe bug into a false pass.
"""

import io
import unittest


def require_assertion_failure(result, name, *, expected_assertion=None):
    """Raise unless the run failed on an assertion; return the failure count."""
    if result.errors:
        first = result.errors[0][1]
        raise AssertionError(
            f"probe crashed instead of failing an invariant ({name}): "
            f"{type(first).__name__}: {first}")
    if not result.failures:
        raise AssertionError(f"bypass was not detected by the expected invariant: {name}")
    if expected_assertion is not None and any(
        expected_assertion not in traceback for _, traceback in result.failures
    ):
        raise AssertionError(f"target invariant was not reached: {name}")
    return len(result.failures)


def run_case(case):
    """Run one test case, returning its result without printing to stderr."""
    return unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(case)
