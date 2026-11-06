"""First Job exceptions retain code locations without private error text."""

import unittest
from unittest.mock import patch

from tests.star_product_support import StarJobFixture


class JobFailureDiagnosticsTest(StarJobFixture, unittest.TestCase):
    def test_public_failure_logs_type_and_location_without_exception_message(self):
        self.open_star([])
        pipeline = self.app.extensions["showcase_workspace_service"].star_pipeline
        with (patch.object(pipeline, "run", side_effect=RuntimeError("private-prompt-and-key")),
              self.assertLogs("showcase.job_failure", level="ERROR") as observed):
            job = self.terminal(self.create_job())
        self.assertEqual("failed", job["status"])
        self.assertEqual("job_execution_failed", job["error"])
        logs = " ".join(observed.output)
        self.assertIn("exception_type=RuntimeError", logs)
        self.assertIn("workspace.py", logs)
        self.assertNotIn("private-prompt-and-key", logs)


if __name__ == "__main__":
    unittest.main()
