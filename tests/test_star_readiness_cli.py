"""The #97 runner requires explicit authorization before any live dispatch."""

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.run_star_readiness_97 import (
    ARTIFACTS,
    _build_adapter,
    _claim_live_registration,
    _inside_artifacts,
    build_parser,
)


class StarReadinessCliTest(unittest.TestCase):
    def test_freeze_and_run_commands_require_explicit_confirmation(self):
        cases = (
            ["freeze-live"],
            ["run-live", "--manifest", "artifacts/registration.json",
             "--manifest-sha256", "a" * 64, "--archive", "artifacts/run"],
        )
        for args in cases:
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    build_parser().parse_args(args)
            self.assertEqual(2, raised.exception.code)

    def test_artifact_paths_cannot_escape_the_ignored_root(self):
        with self.assertRaisesRegex(ValueError, "artifact_path_invalid"):
            _inside_artifacts(ARTIFACTS.parent / "outside")

        allowed = _inside_artifacts(Path("artifacts") / "issue-97-live" / "run-1")
        self.assertTrue(allowed.is_relative_to(ARTIFACTS.resolve()))

    def test_adapter_pins_live_settings_without_dispatching(self):
        environment = {
            "INTERN_API_KEY": "test-only-not-a-real-key",
            "INTERN_API_BASE": "https://chat.intern-ai.org.cn/api/v1/chat/completions",
            "INTERN_MODEL": "intern-s2",
        }
        with patch.dict(os.environ, environment):
            adapter = _build_adapter({
                "provider_endpoint": environment["INTERN_API_BASE"],
            })

        client = adapter._get_client()
        self.assertEqual(180, client.timeout)
        self.assertEqual(3, client.retry)
        self.assertTrue(client.thinking_mode)
        self.assertTrue(client.provider_endpoint_only)
        self.assertFalse(client.loopback_only)

    def test_live_registration_can_only_be_claimed_once_by_content_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("scripts.run_star_readiness_97.ARTIFACTS", Path(directory)):
                _claim_live_registration("a" * 64)
                with self.assertRaisesRegex(ValueError, "already_consumed"):
                    _claim_live_registration("a" * 64)

                _claim_live_registration("b" * 64)


if __name__ == "__main__":
    unittest.main()
