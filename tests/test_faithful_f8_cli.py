"""Public Faithful CLI preserves registration and refuses overwritten evidence."""

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path


class FaithfulEvaluationCliTest(unittest.TestCase):
    def test_help_is_explicit_and_performs_no_dispatch(self):
        from showcase.faithful_eval import main

        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as stopped:
            main(["--help"])
        self.assertEqual(0, stopped.exception.code)
        self.assertIn("register", output.getvalue())
        self.assertIn("replay", output.getvalue())

    def test_sealed_evidence_is_create_once_and_detects_tampering(self):
        from showcase.faithful_eval_store import read_sealed, write_sealed

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.json"
            write_sealed(path, {"status": "unknown"})
            self.assertEqual({"status": "unknown"}, read_sealed(path))
            with self.assertRaises((ValueError, FileExistsError)):
                write_sealed(path, {"status": "completed"})
            path.write_text('{"status":"completed"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                read_sealed(path)

    def test_json_duplicate_fields_and_sensitive_paths_are_rejected(self):
        from showcase.faithful_eval_store import load_json

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_text('{"group":"faithful-A","group":"faithful-B"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_json(path)
            secret = Path(directory) / ".env"
            secret.write_text("credential", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_json(secret)

    def test_artifacts_are_the_supported_evidence_location(self):
        from showcase.faithful_eval_store import read_sealed, write_sealed

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifacts" / "batch" / "record.json"
            write_sealed(path, {"execution_status": "unknown"})
            self.assertEqual("unknown", read_sealed(path)["execution_status"])

    def test_public_registration_replay_keeps_all_slots_and_refuses_overwrite(self):
        from unittest.mock import patch

        from showcase.faithful_eval import main
        from showcase.faithful_eval_contract import digest
        from tests.test_faithful_f8_contract import manifest_fixture

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = manifest_fixture()
            manifest["protocol_sha256"] = protocol_digest()
            baseline = Path(__file__).resolve().parents[1] / "BASELINE.json"
            manifest["baseline_sha256"] = hashlib.sha256(baseline.read_bytes()).hexdigest()
            manifest["groups"]["faithful-E"]["capability_status"] = "unsupported"
            path = root / "manifest.json"
            dump_json(path, manifest)
            source = {"revision": manifest["source_revision"], "source_sha256": "a" * 64,
                      "dirty_status": "clean", "dirty_paths": []}
            args = ["register", "--manifest", str(path), "--sha256", digest(manifest),
                    "--root", str(root / "artifacts")]
            output = io.StringIO()
            with patch("showcase.experiment_sources.source_identity", return_value=source):
                with contextlib.redirect_stdout(output):
                    self.assertEqual(0, main(args))
                batch = root / "artifacts" / manifest["batch_id"]
                before = {p.relative_to(batch).as_posix(): p.read_bytes() for p in batch.rglob("*") if p.is_file()}
                with contextlib.redirect_stdout(output):
                    self.assertEqual(0, main(["replay", "--batch", str(batch)]))
                    self.assertEqual(1, main(args))
                after = {p.relative_to(batch).as_posix(): p.read_bytes() for p in batch.rglob("*") if p.is_file()}
                self.assertEqual(before, after)
            report = json.loads(output.getvalue().splitlines()[1])
            self.assertEqual(7, sum(g["N_registered"] for g in report["groups"].values()))
            self.assertEqual(1, report["groups"]["faithful-E"]["counts"]["unsupported"])

    def test_replay_rejects_extra_l1_files(self):
        from unittest.mock import patch

        from showcase.faithful_eval import replay

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "l1"
            path.mkdir()
            (path / "private.txt").write_text("not public evidence", encoding="utf-8")
            from tests.test_faithful_f8_contract import manifest_fixture
            source = {"revision": "1" * 40, "source_sha256": "a" * 64,
                      "dirty_status": "clean", "dirty_paths": []}
            with patch("showcase.faithful_eval.read_batch", return_value=(manifest_fixture(), [], {}, source)):
                with self.assertRaises(ValueError):
                    replay(Path(directory))


def protocol_digest():
    """Use the actual frozen protocol, without reading any reserved test file."""
    path = Path(__file__).resolve().parents[1] / "docs/engineering/faithful-f8-protocol-20261111.md"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
