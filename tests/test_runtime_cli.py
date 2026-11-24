"""Offline contracts for the independent RiCL Runtime CLI."""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ricl_runtime import DeterministicModelPort, Runtime

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class RuntimeOfflineTests(unittest.TestCase):
    """Exercise the Runtime and command-line public boundaries without a Provider."""

    def test_run_persists_answer_verification_budget_and_redacted_trace(self) -> None:
        answer = "Adding the two numbers gives 4."
        with tempfile.TemporaryDirectory() as directory:
            result = Runtime(DeterministicModelPort(answer)).run(
                problem="Compute 2 + 2.",
                problem_id="addition-example",
                condition_id="offline-baseline",
                output_root=Path(directory),
            )

            run_dir = Path(directory) / result["run_id"]
            saved = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            trace = (run_dir / "trace.jsonl").read_text(encoding="utf-8")
            events = [json.loads(line) for line in trace.splitlines()]

        self.assertEqual(saved, result)
        self.assertEqual(result["result"]["answer"], answer)
        self.assertEqual(result["verification"]["status"], "verified")
        self.assertEqual(result["verification"]["scope"], "integer arithmetic reference check")
        self.assertEqual(result["problem"]["id"], "addition-example")
        self.assertEqual(result["condition_id"], "offline-baseline")
        self.assertEqual(result["run"]["status"], "completed")
        self.assertEqual(result["run"]["stop_reason"], "answer_generated")
        self.assertTrue(result["source"]["revision"])
        self.assertEqual(len(result["config_sha256"]), 64)
        self.assertEqual(result["model"]["requested"], "deterministic-offline")
        self.assertEqual(result["model"]["actual"], "deterministic-offline")
        self.assertEqual(result["budget"]["model_requests"], {"limit": 1, "used": 1})
        self.assertEqual(result["usage"]["tokens"], "unknown")
        self.assertEqual(result["cost"]["amount_usd"], "unknown")
        self.assertEqual(events[-1]["event"], "run_stopped")
        self.assertNotIn("Compute 2 + 2.", trace)
        self.assertNotIn(answer, trace)
        self.assertEqual(
            events[1]["answer_sha256"], hashlib.sha256(answer.encode("utf-8")).hexdigest()
        )

    def test_missing_independent_criterion_is_explicitly_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = Runtime(DeterministicModelPort("Every prime is odd.")).run(
                problem="Prove every prime number is odd.",
                problem_id="unsupported-proof",
                condition_id="offline-baseline",
                output_root=Path(directory),
            )

        self.assertEqual(result["verification"]["status"], "unknown")
        self.assertEqual(result["verification"]["scope"], "none")
        self.assertEqual(result["verification"]["reason"], "no_applicable_criterion")
        self.assertEqual(result["result"]["answer"], "Every prime is odd.")

    def test_incorrect_integer_candidate_is_not_verified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = Runtime(DeterministicModelPort("The answer is 5.")).run(
                problem="Compute 2 + 2.",
                output_root=Path(directory),
            )

        self.assertEqual(result["verification"]["status"], "failed")
        self.assertEqual(result["verification"]["reason"], "answer_differs_from_reference")

    def test_cli_output_matches_saved_offline_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ricl_runtime",
                    "--problem",
                    "Compute 2 + 2.",
                    "--offline-answer",
                    "The sum is 4.",
                    "--problem-id",
                    "addition-example",
                    "--condition-id",
                    "offline-baseline",
                    "--output-root",
                    directory,
                ],
                cwd=REPOSITORY_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            result = json.loads(completed.stdout)
            run_dir = Path(directory) / result["run_id"]
            saved = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            trace = (run_dir / "trace.jsonl").read_text(encoding="utf-8")

        self.assertEqual(saved, result)
        self.assertEqual(result["result"]["answer"], "The sum is 4.")
        self.assertEqual(result["verification"]["status"], "verified")
        self.assertTrue(trace)


if __name__ == "__main__":
    unittest.main()
