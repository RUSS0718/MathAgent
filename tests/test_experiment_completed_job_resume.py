from __future__ import annotations

import tempfile
import unittest

from showcase.experiment_execution import resume_batch, run_batch
from showcase.experiment_manifest import manifest_digest
from showcase.experiment_runner import read_status
from tests.test_showcase_experiment_cli import _manifest
from tests.test_showcase_experiment_execution import _context_for_run, _JobAdapter


class CompletedJobResumeTest(unittest.TestCase):
    def test_reconciles_successful_job_without_submitting_resume_action(self):
        """A completed remote Job is observed and accounted for exactly once."""
        source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }
        manifest = _manifest(source)
        digest = manifest_digest(manifest)
        adapter = _JobAdapter([{"status": "running"}])
        with tempfile.TemporaryDirectory() as temporary:
            initial = run_batch(
                manifest,
                expected_sha256=digest,
                run_id="run-completed-job-resume",
                output_root=temporary,
                context=_context_for_run(
                    manifest, adapter, "run-completed-job-resume"
                ),
            )
            self.assertEqual("running", initial["phase"])
            record = read_status(
                "run-completed-job-resume", output_root=temporary
            )["run_records"][0]
            recovery = adapter.resume_preflight(
                record["job_id"], record["deadline_at"], intent=record
            )
            recovery["status"] = "succeeded"
            adapter.resume_response = recovery

            resumed = resume_batch(
                "run-completed-job-resume",
                expected_sha256=digest,
                output_root=temporary,
                context=_context_for_run(
                    manifest, adapter, "run-completed-job-resume"
                ),
            )

        self.assertEqual("completed", resumed["phase"])
        self.assertEqual(1, resumed["completed"])
        self.assertEqual(1, adapter.submissions)
        self.assertEqual(0, adapter.resume_submissions)
