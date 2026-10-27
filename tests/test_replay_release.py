"""Replay artifact and credential-free release gate contracts."""

from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from scripts import check_showcase_release
from showcase.replay import load_replay, write_sample_replay

ROOT = Path(__file__).resolve().parents[1]


class ReplayReleaseTest(unittest.TestCase):
    def test_v02_release_evidence_keeps_live_gate_honest(self):
        evidence = json.loads(
            (ROOT / "docs" / "evals" / "v0.2-release-evidence.json").read_text(encoding="utf-8")
        )
        self.assertIn(evidence["release_status"], {"engineering-preview", "unavailable"})
        self.assertEqual("unavailable", evidence["acceptance"]["AC-06"]["status"])
        self.assertEqual("planned", evidence["math_effect_evaluation"]["status"])
        self.assertTrue(
            {"live", "fake", "replay", "experimental", "unavailable", "planned"}.issubset(
                evidence["labels"]
            )
        )

    def test_checked_in_replay_is_explicit_and_redacted(self):
        path = ROOT / "docs" / "replay" / "showcase-replay-v0.1.json"
        replay = load_replay(path)
        self.assertEqual("replay", replay["run_mode"])
        serialized = json.dumps(replay, ensure_ascii=False).lower()
        self.assertNotIn("api_key", serialized)
        self.assertNotIn("full_image", serialized)

    def test_sample_replay_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "replay.json"
            written = write_sample_replay(path)
            loaded = load_replay(path)
            self.assertEqual("replay", loaded["run_mode"])
            self.assertEqual(written["run"]["run_id"], loaded["run"]["run_id"])

    def test_release_gate_is_credential_free(self):
        completed = unittest.mock.Mock(returncode=0, stdout="", stderr="")
        output = StringIO()
        with (
            patch.object(check_showcase_release.subprocess, "run", return_value=completed) as run,
            patch.object(check_showcase_release, "check_baseline") as baseline,
            patch.object(check_showcase_release, "check_release_evidence") as evidence,
            patch("sys.argv", ["check_showcase_release.py"]),
            redirect_stdout(output),
        ):
            self.assertEqual(0, check_showcase_release.main())
        self.assertIn("showcase_release=PASS", output.getvalue())
        self.assertTrue(
            any("scripts/run_unittest_report.py" in call.args[0] for call in run.call_args_list)
        )
        baseline.assert_called_once()
        evidence.assert_called_once()

    def test_release_gate_strict_mode_passes_flag_to_test_runner(self):
        completed = unittest.mock.Mock(returncode=0, stdout="", stderr="")
        with (
            patch.object(check_showcase_release.subprocess, "run", return_value=completed) as run,
            patch.object(check_showcase_release, "check_baseline"),
            patch.object(check_showcase_release, "check_release_evidence"),
            patch("sys.argv", ["check_showcase_release.py", "--require-reference"]),
            redirect_stdout(StringIO()),
        ):
            self.assertEqual(0, check_showcase_release.main())
        self.assertTrue(any("--require-reference" in call.args[0] for call in run.call_args_list))


if __name__ == "__main__":
    unittest.main()
