"""C11 S03 ProblemSpec survives process exit and explicit unknown retry."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.star_recovery_worker import S03_SPEC


class FaithfulS03RecoveryTest(unittest.TestCase):
    def test_problem_spec_and_deadline_survive_process_exit_and_explicit_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            crashed = subprocess.run(
                [sys.executable, "-m", "tests.star_recovery_worker", directory, "spec_unknown"],
                capture_output=True, timeout=30,
            )
            self.assertEqual(71, crashed.returncode, crashed.stderr.decode(errors="replace"))
            job_id = (folder / "job_id").read_text(encoding="utf-8")
            before = [json.loads(line) for line in
                      (folder / "requests.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(["explore", "planner", "reasoner"],
                             [item["role"] for item in before])

            resumed = subprocess.run(
                [sys.executable, "-m", "tests.star_recovery_worker", directory, "spec_resume"],
                capture_output=True, timeout=30,
            )
            self.assertEqual(0, resumed.returncode, resumed.stderr.decode(errors="replace"))
            self.assertEqual("202", (folder / "resume_status").read_text(encoding="utf-8"))
            final_job = json.loads((folder / "final_job.json").read_text(encoding="utf-8"))
            self.assertEqual(job_id, final_job["job_id"])
            self.assertEqual("succeeded", final_job["status"], final_job)
            self.assertEqual(float((folder / "interrupted_deadline.txt").read_text()),
                             final_job["result"]["budget"]["deadline_at"])
            self.assertEqual(1, final_job["result"]["budget"]["unknown_attempts"])
            self.assertEqual(7, final_job["result"]["budget"]["http_attempts"])
            self.assertEqual(S03_SPEC,
                             json.loads((folder / "problem_spec.json").read_text(encoding="utf-8")))

            requests = [json.loads(line) for line in
                        (folder / "requests.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(7, len(requests))
            self.assertEqual(2, sum(item["role"] == "reasoner" for item in requests))
            self.assertTrue(all(item.get("problem_spec_version") == 1 for item in requests))
            self.assertEqual(
                {"covered": 1, "total": 1,
                 "items": [{"ordinal": 1, "type": "universal", "status": "satisfied"}]},
                final_job["result"]["solver"]["progress"]["root_obligations"],
            )


if __name__ == "__main__":
    unittest.main()
