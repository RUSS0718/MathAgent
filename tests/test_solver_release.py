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
