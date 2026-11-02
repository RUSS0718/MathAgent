"""Source identity tests for the #97 readiness experiment archive."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from showcase import star_experiment_archive


class SourceIdentityTest(unittest.TestCase):
    def test_release_gate_and_test_runner_changes_change_source_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            showcase = root / "showcase"
            scripts = root / "scripts"
            showcase.mkdir()
            scripts.mkdir()
            (showcase / "star_experiment_archive.py").write_text("# fixture\n", encoding="utf-8")
            source_files = (
                "scripts/check_showcase_release.py",
                "scripts/check_workspace.py",
                "scripts/check_solver_release.py",
                "scripts/run_unittest_report.py",
            )
            for name in source_files:
                (root / name).write_text("# original\n", encoding="utf-8")

            subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Test",
                    "-c",
                    "user.email=test@example.test",
                    "commit",
                    "--quiet",
                    "--allow-empty",
                    "-m",
                    "fixture",
                ],
                cwd=root,
                check=True,
            )

            with patch.object(
                star_experiment_archive,
                "__file__",
                str(showcase / "star_experiment_archive.py"),
            ):
                for name in source_files:
                    with self.subTest(source=name):
                        for source in source_files:
                            (root / source).write_text("# original\n", encoding="utf-8")
                        original_identity = star_experiment_archive.source_identity()
                        path = root / name
                        path.write_text(
                            path.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8"
                        )
                        changed_identity = star_experiment_archive.source_identity()
                        self.assertNotEqual(
                            original_identity["source_sha256"],
                            changed_identity["source_sha256"],
                            f"{name} must be in the fixed source hash scope",
                        )

    def test_retained_untracked_test_markdown_is_excluded_from_source_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            showcase = root / "showcase"
            tests = root / "tests"
            showcase.mkdir()
            tests.mkdir()
            (showcase / "star_experiment_archive.py").write_text("# fixture\n", encoding="utf-8")
            retained = tests / "test.md"
            retained.write_text("caller-owned content A\n", encoding="utf-8")

            subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Test",
                    "-c",
                    "user.email=test@example.test",
                    "commit",
                    "--quiet",
                    "--allow-empty",
                    "-m",
                    "fixture",
                ],
                cwd=root,
                check=True,
            )

            with patch.object(
                star_experiment_archive,
                "__file__",
                str(showcase / "star_experiment_archive.py"),
            ):
                original_identity = star_experiment_archive.source_identity()
                retained.write_text("caller-owned content B\n", encoding="utf-8")
                changed_identity = star_experiment_archive.source_identity()

            self.assertEqual(original_identity, changed_identity)


if __name__ == "__main__":
    unittest.main()
