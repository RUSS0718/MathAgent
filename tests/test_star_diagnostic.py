import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from showcase.star_diagnostic import DiagnosticJob
from showcase.star_diagnostic_registration import freeze
from tests.star_diagnostic_support import plan


class DiagnosticTest(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(self.directory)
        self.registration = self.root / "registration"
        self.manifest = freeze(plan(), self.registration)
        self.job = DiagnosticJob(self.registration, self.root / "archive", self.root / "registry.db")

    def test_socket_free_order_and_duplicate_across_directories(self):
        with patch("socket.socket", side_effect=AssertionError("socket forbidden")):
            result = self.job.run()
        self.assertEqual("completed", result["status"])
        self.assertEqual([r["run_id"] for r in self.manifest["requests"]],
                         [r["run_id"] for r in result["results"]])
        self.assertEqual(2, result["dispatched"])
        self.assertEqual(20, result["charged_tokens"])
        other = DiagnosticJob(self.registration, self.root / "other", self.root / "registry.db")
        with self.assertRaisesRegex(ValueError, "consumed"):
            other.run()

    def test_unknown_stops_batch_and_late_original_usage_is_idempotent(self):
        result = self.job.run(outcomes=["unknown", "success"])
        self.assertEqual("unknown", result["status"])
        self.assertEqual(1, result["dispatched"])
        original = result["results"][0]
        self.assertGreater(result["reserved_tokens"], 16384)
        self.assertIsNone(result["provider_known"]["total_tokens"])
        args = (original["run_id"], original["attempt_id"])
        self.assertTrue(self.job.reconcile(*args, prompt_tokens=7, completion_tokens=3, total_tokens=10))
        self.assertFalse(self.job.reconcile(*args, prompt_tokens=7, completion_tokens=3, total_tokens=10))
        after = self.job.snapshot()
        self.assertEqual("unknown", after["status"])
        self.assertEqual(10, after["charged_tokens"])
        self.assertEqual(original["deadline_at"], after["results"][0]["deadline_at"])
        with self.assertRaisesRegex(ValueError, "consumed"):
            self.job.run()

    def test_intent_crash_reserves_full_envelope_and_restart_never_resends(self):
        result = self.job.run(outcomes=["intent_crash", "success"])
        self.assertEqual("interrupted", result["status"])
        self.assertEqual(65536, result["unconfirmed_reserved_tokens"])
        self.assertIsNone(result["charged_tokens"])
        with self.assertRaisesRegex(ValueError, "consumed"):
            self.job.run()

    def test_p_control_continuation_reuses_prior_results_and_total_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = freeze(plan("P", 4), root / "registration")
            job = DiagnosticJob(root / "registration", root / "archive", root / "registry.db")
            first = job.run(limit=3)
            self.assertEqual("control_complete", first["status"])
            self.assertEqual(3, first["dispatched"])
            after = job.continue_remaining()
            self.assertEqual("completed", after["status"])
            self.assertEqual(4, after["dispatched"])
            self.assertEqual(40, after["charged_tokens"])
            self.assertEqual(first["results"], after["results"][:3])
            self.assertEqual(manifest["sha256"], after["manifest_sha256"])
