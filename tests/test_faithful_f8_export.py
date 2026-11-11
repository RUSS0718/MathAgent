"""Faithful export binds every member without exposing private inputs."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class FaithfulExportTest(unittest.TestCase):
    def test_export_cannot_write_inside_its_source_batch(self):
        from showcase.faithful_eval_export import export_batch

        with tempfile.TemporaryDirectory() as directory:
            batch = Path(directory)
            for name in ("records", "reviews", "l1"):
                (batch / name).mkdir()
            from showcase.faithful_eval_reporting import build_report

            with patch("showcase.faithful_eval_export.read_batch", return_value=self._fixtures()), \
                    patch("showcase.faithful_eval_export.replay", return_value=build_report(self._fixtures()[0], [])):
                with self.assertRaises(ValueError):
                    export_batch(batch, batch / "package")
            self.assertFalse((batch / "package").exists())

    def test_failed_l1_without_summary_remains_readable_as_failure(self):
        from subprocess import CompletedProcess

        from showcase.faithful_eval_export import read_l1, run_l1

        with tempfile.TemporaryDirectory() as directory:
            batch = Path(directory)
            (batch / "l1").mkdir()
            manifest, records, reviews, source = self._fixtures()
            with patch("showcase.faithful_eval_export.read_batch", return_value=(manifest, records, reviews, source)), \
                    patch("showcase.faithful_eval_export.source_identity", return_value=source), \
                    patch("showcase.faithful_eval_export.subprocess.run", return_value=CompletedProcess([], 2, "", "")):
                with self.assertRaises(ValueError):
                    run_l1(batch)
            self.assertEqual("fail", read_l1(batch, manifest)["status"])

    def test_nonzero_l1_exit_cannot_seal_a_passing_report(self):
        from subprocess import CompletedProcess

        from showcase.faithful_eval_export import run_l1
        from showcase.faithful_eval_store import read_sealed

        with tempfile.TemporaryDirectory() as directory:
            batch = Path(directory)
            (batch / "l1").mkdir()
            manifest, records, reviews, source = self._fixtures()
            def failed_worker(command, **kwargs):
                summary = Path(command[command.index("--summary-json") + 1])
                diagnostics = Path(command[command.index("--diagnostics") + 1])
                summary.write_text(json.dumps({"testsRun": 25, "status": "passed", "skipped": 0,
                                               "failures": 0, "errors": 0}), encoding="utf-8")
                diagnostics.write_text("private-answer-marker", encoding="utf-8")
                return CompletedProcess(command, 1, "", "")
            with patch("showcase.faithful_eval_export.read_batch", return_value=(manifest, records, reviews, source)), \
                    patch("showcase.faithful_eval_export.source_identity", return_value=source), \
                    patch("showcase.faithful_eval_export.subprocess.run", side_effect=failed_worker):
                with self.assertRaises(ValueError):
                    run_l1(batch)
            self.assertEqual("fail", read_sealed(batch / "l1/result.json")["status"])

    def test_public_l1_export_omits_raw_private_output(self):
        from showcase.faithful_eval_export import _copy_l1

        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / "source", Path(directory) / "target"
            source.mkdir()
            target.mkdir()
            (source / "console.log").write_text("private-answer-marker", encoding="utf-8")
            (source / "diagnostics.log").write_text("private-answer-marker", encoding="utf-8")
            _copy_l1(source, target)
            self.assertFalse(any("private-answer-marker" in path.read_text(encoding="utf-8")
                                 for path in target.iterdir()))

    def test_integrity_index_covers_report_and_export_receipt_binds_index(self):
        from showcase.faithful_eval import write_sealed
        from showcase.faithful_eval_contract import GROUPS, digest
        from showcase.faithful_eval_export import export_batch

        with tempfile.TemporaryDirectory() as directory:
            batch = Path(directory) / "batch"
            batch.mkdir()
            output = Path(directory) / "package"
            manifest, records, reviews, source = self._fixtures()
            for name in ("records", "reviews", "l1"):
                (batch / name).mkdir()
            write_sealed(batch / "manifest.json", manifest)
            write_sealed(batch / "source.json", source)
            write_sealed(batch / "registration.json", {
                "schema_version": "faithful-f8-registration-v1", "manifest_sha256": digest(manifest),
                "slots": [{"group": group, "sample_id": "AIME2025/1",
                           "repetition": 0, "execution_status": "not_run"} for group in GROUPS]})
            with patch("showcase.faithful_eval_export.read_batch", return_value=(manifest, records, reviews, source)):
                result = export_batch(batch, output)
            index = json.loads((output / "integrity.json").read_text(encoding="utf-8"))
            report = output / "report.json"
            listed = {item["path"]: item for item in index["members"]}
            self.assertIn("report.json", listed)
            self.assertEqual(report.stat().st_size, listed["report.json"]["bytes"])
            receipt = json.loads(Path(result["receipt_path"]).read_text(encoding="utf-8"))
            self.assertEqual(receipt["integrity_sha256"], result["integrity_sha256"])
            self.assertEqual(result["status"], "exported")
            self.assertNotIn("prompt", report.read_text(encoding="utf-8").lower())

    def test_existing_package_or_receipt_is_never_overwritten(self):
        from showcase.faithful_eval_export import export_batch

        with tempfile.TemporaryDirectory() as directory:
            batch = Path(directory) / "batch"
            batch.mkdir()
            output = Path(directory) / "package"
            output.mkdir()
            with patch("showcase.faithful_eval_export.read_batch", return_value=self._fixtures()):
                with self.assertRaises(ValueError):
                    export_batch(batch, output)

    def test_l1_selector_is_the_exact_frozen_25_ids(self):
        from showcase.faithful_eval_export import frozen_l1_ids

        identifiers = frozen_l1_ids()
        self.assertEqual(len(identifiers), 25)
        self.assertEqual(len(set(identifiers)), 25)
        self.assertTrue(all(name.startswith("tests.test_") for name in identifiers))

    @staticmethod
    def _fixtures():
        from tests.test_faithful_f8_contract import manifest_fixture

        return manifest_fixture(), [], {}, {
            "revision": "1" * 40,
            "source_sha256": "a" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }
