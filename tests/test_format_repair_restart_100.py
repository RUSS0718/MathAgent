"""Persisted credits and unknown reservations through public Job restart."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from showcase.flask_app import create_app
from showcase.solver_harness import SolverHarness
from showcase.star_product_config import limited_config
from tests.format_repair_worker_100 import config
from tests.star_product_support import StarJobFixture


class FormatRepairRestartTest(StarJobFixture, unittest.TestCase):
    def test_f08_real_process_exit_keeps_credit_call_reservation_and_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            process = subprocess.run([sys.executable, "-m", "tests.format_repair_worker_100", directory],
                                     capture_output=True, timeout=25)
            self.assertEqual(71, process.returncode, process.stderr.decode(errors="replace"))
            job_id = (folder / "job_id").read_text()
            before = [json.loads(line) for line in (folder / "requests.jsonl").read_text().splitlines()]
            self.assertEqual(2, len(before))
            self.assertEqual(before[0]["call_id"] + ":serialization-1", before[1]["call_id"])
            with ExitStack() as cleanup, patch.dict(os.environ, {"INTERN_API_KEY": "offline-only"}), patch(
                    "llm_client.requests.post", side_effect=AssertionError("unexpected resend")) as post:
                self.app = create_app(config(folder))
                for name in ("showcase_workspace_service", "showcase_run_service", "loopback_store"):
                    cleanup.callback(self.app.extensions[name].close)
                self.client = self.app.test_client()
                self.csrf = self.client.get("/api/check_auth").get_json()["csrf_token"]
                initial = self.job(job_id)
                budget = initial["result"]["budget"]
                self.assertGreater(budget["reserved_tokens"], 0)
                for _ in range(2):
                    denied = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={},
                                              headers=self.headers())
                    self.assertEqual(409, denied.status_code, denied.get_json())
                after = self.job(job_id)["result"]["budget"]
                self.assertEqual(budget["deadline_at"], after["deadline_at"])
                self.assertEqual(budget["reserved_tokens"], after["reserved_tokens"])
                self.assertEqual(2, after["http_attempts"])
                self.assertEqual(1, after["unknown_attempts"])
                self.assertEqual(0, post.call_count)
                # The public Harness snapshot carries the consumed credit across restart.
                harness_config = limited_config(config(folder)["SHOWCASE_STAR_BUDGET"],
                                                {"serialization_repair": True})
                harness_config["features"]["candidate_registry"] = True
                harness_config["hint_mode"] = "none"
                with SolverHarness(database_path=folder / "showcase.sqlite3", config=harness_config) as harness:
                    state = harness.get_run(job_id)["state"]
                    self.assertEqual({before[0]["call_id"]: before[1]["call_id"]},
                                     state["serialization_repairs"])
                    self.assertNotIn("```", json.dumps(state))


if __name__ == "__main__":
    unittest.main()
