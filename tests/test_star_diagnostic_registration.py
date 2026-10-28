import json
import tempfile
import unittest
from pathlib import Path

from showcase.star_diagnostic_registration import digest, dry_run, freeze, validate
from tests.star_diagnostic_support import plan


class RegistrationTest(unittest.TestCase):
    def test_freeze_is_redacted_and_phase_limits_do_not_double_count(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = freeze(plan(), Path(directory) / "registration")
            report = dry_run(manifest)
            self.assertEqual(36, report["phase_limits"]["P"]["requests"])
            self.assertEqual(2359296, report["phase_limits"]["P"]["tokens"])
            self.assertEqual(900, manifest["requests"][0]["shadow_seconds"])
            self.assertNotIn("Give a complete proof", json.dumps(manifest))
            self.assertEqual(2, report["planned"])
            validate(manifest)

    def test_overlong_proof_is_rejected_without_truncation_or_registration(self):
        with tempfile.TemporaryDirectory() as directory:
            value = plan()
            proof = "proof" * 20000
            value["requests"][0]["prompt"] = proof
            target = Path(directory) / "registration"
            with self.assertRaisesRegex(ValueError, "too_long"):
                freeze(value, target)
            self.assertEqual(proof, value["requests"][0]["prompt"])
            self.assertFalse(target.exists())

    def test_resealed_manifest_cannot_raise_request_or_single_call_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = freeze(plan(), Path(directory) / "registration")
            manifest["requests"][0]["input_estimate"] = 49153
            manifest["sha256"] = digest({k: v for k, v in manifest.items() if k != "sha256"})
            with self.assertRaises(ValueError):
                validate(manifest)
