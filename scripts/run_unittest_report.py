"""Run the repository suite and report each skipped test and its reason."""

from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REFERENCE_TESTS = {
    "test_star_product_full_modes.StarFullModeTest."
    "test_reference_easy_problem_completes_fastpath_review_and_binding",
    "test_star_product_full_modes.StarFullModeTest."
    "test_reference_runs_same_public_job_with_real_tool_and_whole_review",
    "test_star_rb06_recovery.RobustRecoveryTest."
    "test_reference_receipt_exit_resumes_same_job_through_final_review_and_binding",
}


def run_suite(suite, *, stream, required=frozenset()):
    """Require selected tests to be discovered and not skipped when requested."""

    class ReportingResult(unittest.TextTestResult):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.started = set()

        def startTest(self, test):
            self.started.add(test.id())
            super().startTest(test)

        def addSkip(self, test, reason):
            super().addSkip(test, reason)
            self.stream.writeln(f"\nSKIP {test.id()}: {reason}")

        def stopTestRun(self):
            skipped = {test.id() for test, _ in self.skipped}
            expected_failures = {test.id() for test, _ in self.expectedFailures}
            missing = required - self.started
            uncovered = missing | (required & (skipped | expected_failures))
            if uncovered:
                marker = unittest.FunctionTestCase(lambda: None, description="Reference evidence")
                self.errors.append((marker, "Not covered: " + ", ".join(sorted(uncovered))))
            super().stopTestRun()

    return unittest.TextTestRunner(stream=stream, resultclass=ReportingResult).run(suite)


def discover_suite(tests_dir):
    """Discover the repository's non-package test directory."""
    return unittest.TestLoader().discover(str(tests_dir), pattern="test_*.py")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-reference", action="store_true")
    args = parser.parse_args()
    suite = discover_suite(ROOT / "tests")
    required = REFERENCE_TESTS if args.require_reference else frozenset()
    return 0 if run_suite(suite, stream=sys.stderr, required=required).wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
