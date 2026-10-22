"""Release decisions through the credential-free gate CLI."""

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SolverReleaseTest(unittest.TestCase):
    def test_full_live_release_remains_blocked(self):
        result = subprocess.run(
            [sys.executable, "scripts/check_solver_release.py", "--require-live"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(1, result.returncode)
        self.assertIn("live_release=BLOCKED", result.stdout)
        self.assertIn("needs_review", result.stdout)

    def test_evidence_matrix_validates_actual_discoverable_test_ids(self):
        result = subprocess.run(
            [sys.executable, "scripts/check_solver_release.py", "--matrix-only"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("acceptance_matrix=PASS ac=44 sc=43", result.stdout)

    def test_official_entry_retains_json_output_and_baseline_import_boundary(self):
        from scripts.check_showcase_release import check_baseline
        from scripts.check_workspace import check_entry

        check_baseline()
        check_entry()

    def test_matrix_only_cannot_bypass_required_live_gate(self):
        result = subprocess.run(
            [sys.executable, "scripts/check_solver_release.py", "--matrix-only", "--require-live"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(0, result.returncode)

    def test_mapped_executor_rejects_skip_expected_failure_and_missing_execution(self):
        from scripts.check_solver_release import run_mapped_tests

        class Skipped(unittest.TestCase):
            @unittest.skip("not available")
            def test_case(self):
                pass

        class Expected(unittest.TestCase):
            @unittest.expectedFailure
            def test_case(self):
                self.fail("expected")

        class Passed(unittest.TestCase):
            def test_case(self):
                pass

        for case, expected in ((Skipped, False), (Expected, False), (Passed, True)):
            with self.subTest(case=case.__name__):
                suite = unittest.TestSuite([case("test_case")])
                summary = run_mapped_tests([case.__name__], suite=suite)
                self.assertEqual(expected, summary["passed"])
                self.assertEqual(1, summary["executed"])
        summary = run_mapped_tests(["missing"], suite=unittest.TestSuite())
        self.assertFalse(summary["passed"])
        self.assertEqual(0, summary["executed"])
