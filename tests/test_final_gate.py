"""Contract tests for the parameterized final validation entry point."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import run_final_gate


class FakeProcess:
    """Small subprocess replacement that writes deterministic stage output."""

    def __init__(self, returncode: int, pid: int, stdout) -> None:
        self.returncode = returncode
        self.pid = pid
        stdout.write(f"fake stage output for pid {pid}\n")

    def wait(self) -> int:
        """Return the configured process result."""

        return self.returncode


class FinalGateTest(unittest.TestCase):
    """Verify the public CLI contract without running the real gates."""

    def make_root(self, directory: str) -> Path:
        """Create the minimum repository-shaped tree needed by the runner."""

        root = Path(directory) / "repo"
        frontend = root / "showcase" / "frontend" / "chat-frontend"
        frontend.mkdir(parents=True)
        (root / "source.py").write_text("value = 1\n", encoding="utf-8")
        (root / "tests").mkdir()
        (root / "tests" / "test.md").write_text("user-owned\n", encoding="utf-8")
        (root / "artifacts").mkdir()
        (root / "artifacts" / "old.log").write_text("ignored\n", encoding="utf-8")
        (root / "cache").mkdir()
        (root / "cache" / "old.cache").write_text("ignored\n", encoding="utf-8")
        return root

    def test_default_stages_are_parameterized_and_report_is_run_local(self) -> None:
        """Run every default stage with the requested reference option."""

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_root(directory)
            output_dir = root / "artifacts" / "final-gates"
            calls = []

            def fake_popen(command, *, cwd, stdout, stderr, text, env, shell):
                calls.append((command, Path(cwd), Path(stdout.name).name, shell))
                return FakeProcess(0, 4000 + len(calls), stdout)

            with (
                patch.object(run_final_gate.subprocess, "Popen", side_effect=fake_popen),
                patch.object(run_final_gate.shutil, "which", return_value=r"C:\node\npm.cmd"),
            ):
                result = run_final_gate.main(
                    [
                        "--root",
                        str(root),
                        "--output-dir",
                        str(output_dir),
                        "--run-id",
                        "review-01",
                        "--require-reference",
                    ]
                )

            self.assertEqual(0, result)
            run_dir = output_dir / "review-01"
            commands = [call[0] for call in calls]
            self.assertEqual(
                [
                    ["uv", "run", "python", "scripts/check_fast.py"],
                    [
                        "uv",
                        "run",
                        "python",
                        "scripts/check.py",
                        "--offline",
                        "--report-dir",
                        str(run_dir / "repository-check"),
                    ],
                    [
                        "uv",
                        "run",
                        "python",
                        "scripts/check_showcase_release.py",
                        "--require-reference",
                    ],
                    [r"C:\node\npm.cmd", "ci", "--no-audit", "--no-fund"],
                    [r"C:\node\npm.cmd", "audit", "--audit-level=high"],
                    [r"C:\node\npm.cmd", "run", "check"],
                ],
                commands,
            )
            self.assertEqual([root, root, root], [call[1] for call in calls[:3]])
            self.assertEqual([root / "showcase" / "frontend" / "chat-frontend"] * 3,
                             [call[1] for call in calls[3:]])
            self.assertEqual({False}, {call[3] for call in calls})
            self.assertEqual(
                {"fast.log", "offline.log", "release.log", "frontend-install.log",
                 "frontend-audit.log", "frontend-check.log"},
                {call[2] for call in calls},
            )

            status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(os.getpid(), status["pid"])
            self.assertTrue(status["start_time"])
            self.assertEqual("completed", status["current_stage"])
            self.assertEqual(status["total"], status["completed"])
            self.assertEqual("passed", status["final_status"])
            self.assertEqual("passed", status["status"])
            self.assertGreaterEqual(status["elapsed_seconds"], 0)

            manifest = json.loads(
                (run_dir / "source-manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["before"]["source_hash"], manifest["after"]["source_hash"])
            self.assertTrue(manifest["before"]["dirty_tracked_fingerprint"])
            self.assertTrue(manifest["before"]["dirty_untracked_fingerprint"])
            included_paths = {
                item["path"]
                for item in manifest["before"]["files"]["tracked"]
                + manifest["before"]["files"]["untracked"]
            }
            self.assertNotIn("tests/test.md", included_paths)
            self.assertNotIn("artifacts/old.log", included_paths)
            self.assertNotIn("cache/old.cache", included_paths)

    def test_nonzero_stage_stops_and_preserves_exit_code(self) -> None:
        """A failed child is visible and prevents later stages from starting."""

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_root(directory)
            output_dir = Path(directory) / "final-gates"
            calls = []

            def fake_popen(command, *, cwd, stdout, stderr, text, env, shell):
                calls.append(command)
                return FakeProcess(0 if len(calls) == 1 else 7, 5000 + len(calls), stdout)

            with (
                patch.object(run_final_gate.subprocess, "Popen", side_effect=fake_popen),
                patch.object(run_final_gate.shutil, "which", return_value=r"C:\node\npm.cmd"),
            ):
                result = run_final_gate.main(
                    ["--root", str(root), "--output-dir", str(output_dir), "--run-id", "fail-01"]
                )

            self.assertEqual(7, result)
            self.assertEqual(2, len(calls))
            run_dir = output_dir / "fail-01"
            status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("failed", status["final_status"])
            self.assertEqual("offline", status["current_stage"])
            self.assertEqual(1, status["completed"])
            self.assertIn("EXIT_CODE 7", (run_dir / "offline.log").read_text(encoding="utf-8"))
            self.assertFalse((run_dir / "release.log").exists())

    def test_existing_run_is_rejected_without_overwrite(self) -> None:
        """A run ID is immutable once its output directory exists."""

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_root(directory)
            output_dir = Path(directory) / "final-gates"
            run_dir = output_dir / "already-there"
            run_dir.mkdir(parents=True)
            status_path = run_dir / "status.json"
            status_path.write_text("keep me", encoding="utf-8")

            with patch.object(run_final_gate.subprocess, "Popen") as popen:
                result = run_final_gate.main(
                    [
                        "--root",
                        str(root),
                        "--output-dir",
                        str(output_dir),
                        "--run-id",
                        "already-there",
                    ]
                )

            self.assertEqual(2, result)
            popen.assert_not_called()
            self.assertEqual("keep me", status_path.read_text(encoding="utf-8"))

    def test_source_change_is_reported_without_requiring_clean_tree(self) -> None:
        """A dirty starting tree is accepted while a run-time change is surfaced."""

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_root(directory)
            output_dir = Path(directory) / "final-gates"
            calls = []

            def fake_popen(command, *, cwd, stdout, stderr, text, env, shell):
                calls.append(command)
                if len(calls) == 1:
                    (root / "source.py").write_text("value = 2\n", encoding="utf-8")
                return FakeProcess(0, 6000 + len(calls), stdout)

            with (
                patch.object(run_final_gate.subprocess, "Popen", side_effect=fake_popen),
                patch.object(run_final_gate.shutil, "which", return_value=r"C:\node\npm.cmd"),
            ):
                result = run_final_gate.main(
                    ["--root", str(root), "--output-dir", str(output_dir), "--run-id", "changed-01"]
                )

            self.assertEqual(1, result)
            run_dir = output_dir / "changed-01"
            status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("source_changed", status["final_status"])
            manifest = json.loads(
                (run_dir / "source-manifest.json").read_text(encoding="utf-8")
            )
            self.assertNotEqual(manifest["before"]["source_hash"], manifest["after"]["source_hash"])

    def test_source_change_is_detected_when_output_dir_is_root(self) -> None:
        """The run directory is excluded while the repository root remains hashed."""

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_root(directory)
            calls = []

            def fake_popen(command, *, cwd, stdout, stderr, text, env, shell):
                calls.append(command)
                if len(calls) == 1:
                    (root / "source.py").write_text("value = 3\n", encoding="utf-8")
                return FakeProcess(0, 7000 + len(calls), stdout)

            with (
                patch.object(run_final_gate.subprocess, "Popen", side_effect=fake_popen),
                patch.object(run_final_gate.shutil, "which", return_value=r"C:\node\npm.cmd"),
            ):
                result = run_final_gate.main(
                    ["--root", str(root), "--output-dir", str(root), "--run-id", "changed-02"]
                )

            self.assertEqual(1, result)
            run_dir = root / "changed-02"
            status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("source_changed", status["final_status"])
            manifest = json.loads(
                (run_dir / "source-manifest.json").read_text(encoding="utf-8")
            )
            self.assertNotEqual(manifest["before"]["source_hash"], manifest["after"]["source_hash"])
            self.assertIn(
                "source.py",
                {item["path"] for item in manifest["before"]["files"]["untracked"]},
            )


if __name__ == "__main__":
    unittest.main()
