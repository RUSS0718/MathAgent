import json
import tempfile
import unittest
from pathlib import Path

from showcase.star_diagnostic_registration import dry_run, freeze, validate
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
