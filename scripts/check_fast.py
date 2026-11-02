"""Fast credential-free checks before the complete repository gate."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    """Fail early on baseline, entry, test seam, and Demo contract errors."""
    commands = (
        [sys.executable, "scripts/check_test_seams.py"],
        [
            sys.executable,
            "scripts/run_unittest_report.py",
            "tests.test_baseline_snapshot",
            "tests.test_demo_server",
            "tests.test_solver_release.SolverReleaseTest."
            "test_official_entry_retains_json_output_and_baseline_import_boundary",
        ],
        [sys.executable, "demo_server.py", "--help"],
        [sys.executable, "showcase_server.py", "--help"],
    )
    for command in commands:
        completed = subprocess.run(command, cwd=ROOT, check=False)
        if completed.returncode:
            return completed.returncode
    print("fast_check=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
