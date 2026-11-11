"""Faithful export binds every member without exposing private inputs."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class FaithfulExportTest(unittest.TestCase):
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
