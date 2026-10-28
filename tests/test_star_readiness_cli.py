"""The #97 runner requires explicit authorization before any live dispatch."""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts.run_star_readiness_97 import (
    ARTIFACTS,
    DEFAULT_DRAFT,
    DEFAULT_MANIFEST,
    ROOT,
    _build_adapter,
    _inside_artifacts,
    build_parser,
    main,
)
from showcase.star_readiness_registration import MODEL, digest
from tests.test_star_readiness_registration import (
    SOURCE,
    TEST_V3_QUESTION_SPECS,
    synthetic_v3_draft,
)
from tests.test_star_readiness_v5 import TEST_V5_QUESTION_SPECS, v5_draft


class StarReadinessCliTest(unittest.TestCase):
    def test_default_freeze_uses_v5_draft_without_an_iana_timezone_database(self):
        self.assertEqual(
            ROOT / "artifacts" / "issue-97-prereg" / "draft-v5.json",
            DEFAULT_DRAFT,
        )
        self.assertEqual(
            ROOT / "artifacts" / "issue-97-prereg" / "manifest-v5-preview.json",
            DEFAULT_MANIFEST,
        )
        with tempfile.TemporaryDirectory() as directory:
            artifacts = Path(directory) / "artifacts"
            preregistration = artifacts / "issue-97-prereg"
            preregistration.mkdir(parents=True)
            draft = preregistration / "draft-v5.json"
            manifest = preregistration / "live-manifest.json"
            draft.write_text(json.dumps(v5_draft()), encoding="utf-8")
            with (
                patch("scripts.run_star_readiness_97.ROOT", Path(directory)),
                patch("scripts.run_star_readiness_97.ARTIFACTS", artifacts),
                patch("scripts.run_star_readiness_97.DEFAULT_DRAFT", draft),
                patch("scripts.run_star_readiness_97.DEFAULT_MANIFEST", manifest),
                patch("showcase.star_readiness_registration.V5_QUESTION_SPECS", TEST_V5_QUESTION_SPECS),
                patch(
                    "showcase.star_readiness_coordinator.current_source_identity",
                    return_value=SOURCE,
                ),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                result = main(["freeze-live"])

            self.assertEqual(0, result)
            frozen = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertFalse(frozen["execution_authorized"])
            self.assertEqual("draft_not_dispatchable", frozen["status"])
            self.assertIsNone(frozen["authorization_date"])
            self.assertEqual("issue-97-nonstream-draft-v5", frozen["draft_version"])

    def test_explicit_v3_draft_remains_freezable_for_history(self):
        with tempfile.TemporaryDirectory() as directory:
            artifacts = Path(directory) / "artifacts"
            preregistration = artifacts / "issue-97-prereg"
            preregistration.mkdir(parents=True)
            draft = preregistration / "legacy-v3-draft.json"
            manifest = preregistration / "legacy-v3-manifest.json"
            draft.write_text(json.dumps(synthetic_v3_draft()), encoding="utf-8")
            with (
                patch("scripts.run_star_readiness_97.ROOT", Path(directory)),
                patch("scripts.run_star_readiness_97.ARTIFACTS", artifacts),
                patch(
                    "showcase.star_readiness_registration.V3_QUESTION_SPECS",
                    TEST_V3_QUESTION_SPECS,
                ),
                patch(
                    "showcase.star_readiness_coordinator.current_source_identity",
                    return_value=SOURCE,
                ),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                result = main([
                    "freeze-live", "--draft", str(draft),
                    "--manifest", str(manifest),
                ])

            self.assertEqual(0, result)
            frozen = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual("issue-97-nonstream-draft-v3", frozen["draft_version"])

    def test_freeze_help_describes_supported_drafts_without_claiming_v3(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit) as raised:
                build_parser().parse_args(["--help"])

        self.assertEqual(0, raised.exception.code)
        self.assertIn("supported draft", output.getvalue())
        self.assertNotIn("v3", output.getvalue())

    def test_direct_freeze_command_resolves_repository_modules_before_reading_draft(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            missing_draft = Path(directory) / "missing-draft.json"
            manifest = Path(directory) / "manifest.json"
            environment = os.environ.copy()
            for name in ("INTERN_API_KEY", "INTERN_API_BASE", "INTERN_MODEL"):
                environment.pop(name, None)
            result = subprocess.run(
                [sys.executable, "-B", "scripts/run_star_readiness_97.py", "freeze-live",
                 "--draft", str(missing_draft), "--manifest", str(manifest)],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=False,
                env=environment,
            )
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertEqual({"error": "FileNotFoundError"}, json.loads(result.stderr))
        self.assertFalse(manifest.exists())

    def test_authorize_and_run_commands_require_explicit_confirmation(self):
        cases = (
            ["authorize-live", "--manifest", "artifacts/preview.json",
             "--manifest-sha256", "a" * 64],
            ["run-live", "--manifest", "artifacts/registration.json",
             "--manifest-sha256", "a" * 64, "--archive", "artifacts/run"],
        )
        for args in cases:
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    build_parser().parse_args(args)
            self.assertEqual(2, raised.exception.code)

    def test_authorize_requires_reviewed_preview_hash_and_preserves_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            artifacts = Path(directory) / "artifacts"
            artifacts.mkdir()
            draft = artifacts / "draft.json"
            preview = artifacts / "preview.json"
            live = artifacts / "live.json"
            draft.write_text(json.dumps(synthetic_v3_draft()), encoding="utf-8")
            with (
                patch("scripts.run_star_readiness_97.ROOT", Path(directory)),
                patch("scripts.run_star_readiness_97.ARTIFACTS", artifacts),
                patch("showcase.star_readiness_registration.V3_QUESTION_SPECS", TEST_V3_QUESTION_SPECS),
                patch("showcase.star_readiness_coordinator.current_source_identity", return_value=SOURCE),
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(0, main(["freeze-live", "--draft", str(draft), "--manifest", str(preview)]))
                before = preview.read_bytes()
                frozen = json.loads(before)
                common = ["authorize-live", "--manifest", str(preview),
                          "--authorized-manifest", str(live), "--confirm-live", "--manifest-sha256"]
                self.assertEqual(1, main([*common, "0" * 64]))
                self.assertFalse(live.exists())
                self.assertEqual(0, main([*common, digest(frozen)]))
                self.assertEqual(before, preview.read_bytes())
                authorized = json.loads(live.read_text(encoding="utf-8"))
                self.assertTrue(authorized["execution_authorized"])
                self.assertEqual("authorized_live", authorized["status"])
                self.assertEqual(frozen["questions"], authorized["questions"])
                self.assertEqual(frozen["model"], authorized["model"])
                self.assertEqual(frozen["schedule"], authorized["schedule"])
                self.assertEqual(1, main([*common, digest(frozen)]), "Live file must not be overwritten")

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
                "model": MODEL,
                "provider_endpoint": environment["INTERN_API_BASE"],
            })

        client = adapter._get_client()
        self.assertEqual(180, client.timeout)
        self.assertEqual(3, client.retry)
        self.assertTrue(client.thinking_mode)
        self.assertTrue(client.provider_endpoint_only)
        self.assertFalse(client.loopback_only)

    def test_run_live_delegates_consumption_to_coordinator(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = {"fixture": "live-manifest"}
            manifest_sha256 = digest(manifest)
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            archive_path = root / "archive"
            runner = Mock(return_value={"stop_reason": "completed"})
            coordinator = SimpleNamespace(run=runner)

            with (
                patch("scripts.run_star_readiness_97.ARTIFACTS", root),
                patch("scripts.run_star_readiness_97._build_adapter", return_value=object()),
                patch(
                    "showcase.star_readiness_coordinator.StarReadinessCoordinator",
                    return_value=coordinator,
                ) as factory,
                patch("showcase.star_readiness_coordinator.ARTIFACTS", root / "claims"),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                result = main([
                    "run-live", "--manifest", str(manifest_path),
                    "--manifest-sha256", manifest_sha256,
                    "--archive", str(archive_path), "--execute-live",
                ])

            self.assertEqual(0, result)
            factory.assert_called_once()
            runner.assert_called_once_with()
            self.assertFalse((root / "claims" / "issue-97-prereg" /
                              f"{manifest_sha256}.consumed").exists())


if __name__ == "__main__":
    unittest.main()
