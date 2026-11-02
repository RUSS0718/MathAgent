from __future__ import annotations

import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class ExperimentSourcesTest(unittest.TestCase):
    def test_source_module_exports_pure_config_and_sample_adapters(self) -> None:
        from showcase.experiment_sources import (
            FileSampleHashResolver,
            ModelConfigAdapter,
            StaticModelConfigAdapter,
        )

        applied = {"model": "test-model"}
        adapter = StaticModelConfigAdapter(applied)
        self.assertTrue(callable(adapter.config))
        self.assertEqual("showcase.experiment_sources", ModelConfigAdapter.__module__)
        snapshot = adapter.config()
        snapshot["model"] = "changed"
        self.assertEqual({"model": "test-model"}, adapter.config())

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "samples"
            root.mkdir()
            sample = root / "one.txt"
            sample.write_bytes(b"sample text\n")
            resolver = FileSampleHashResolver(
                root,
                {"sample-1": {"input": "one.txt", "text": "one.txt"}},
            )
            expected = hashlib.sha256(b"sample text\n").hexdigest()
            self.assertEqual(
                {"input_sha256": expected, "text_sha256": expected},
                resolver.hashes({"source_ref": "sample-1"}),
            )

    def test_source_identity_filters_reserved_path_before_reading(self) -> None:
        from showcase.experiment_sources import source_identity

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "showcase").mkdir()
            (root / "tests").mkdir()
            (root / "showcase" / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "tests" / "test.md").write_text("reserved content", encoding="utf-8")
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Experiment test"], cwd=root, check=True)
            subprocess.run(["git", "add", "showcase/sample.py"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "initial"], cwd=root, check=True)

            original = Path.read_bytes

            def guarded_read(path: Path) -> bytes:
                if path == root / "tests" / "test.md":
                    raise AssertionError("reserved file was read")
                return original(path)

            with patch.object(Path, "read_bytes", guarded_read):
                result = source_identity(root)
            self.assertEqual("clean", result["dirty_status"])
            self.assertEqual([], result["dirty_paths"])

    def test_sample_path_rejection_does_not_read_or_echo_source(self) -> None:
        from showcase.experiment_sources import FileSampleHashResolver

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "samples"
            root.mkdir()
            (Path(temporary) / "private.txt").write_text("private prompt", encoding="utf-8")
            resolver = FileSampleHashResolver(
                root,
                {"sample-1": {"input": "../private.txt", "text": "../private.txt"}},
            )
            with patch.object(Path, "read_bytes", side_effect=AssertionError("unexpected read")) as read:
                with self.assertRaisesRegex(ValueError, "experiment_sample_source_invalid") as caught:
                    resolver.hashes({"source_ref": "sample-1"})
            read.assert_not_called()
            self.assertNotIn("private prompt", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
