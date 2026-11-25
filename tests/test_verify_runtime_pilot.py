import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.verify_runtime_pilot import EvidenceError, check_archive


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


class TestRuntimePilotArchive(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.revision = "3" * 40
        self.run_id = "run_a"
        self.run_path = "batch/01-q-aprs/run_a/run.json"
        self.trace_path = "batch/01-q-aprs/run_a/trace.jsonl"
        self.config = {"scope": "配对", "cap": 8}
        self.config_hash = sha(encoded(self.config))
        self.anchor = {"archive": "fixture", "phase": "stopped", "runs": 1}

    def write_bundle(self, *, config=None, with_trace=True):
        run = {
            "run_id": self.run_id,
            "problem": {"id": "q"},
            "condition_id": "aprs",
            "config": self.config if config is None else config,
            "config_sha256": self.config_hash,
            "source": {"revision": self.revision},
        }
        files = {self.run_path: encoded(run)}
        if with_trace:
            files[self.trace_path] = b'{"event":"run_started"}\n'
        for path, value in files.items():
            file = self.root / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(value)
        index = {
            "schema_version": 1,
            "phase": "stopped",
            "revision": self.revision,
            "files_sha256": {key: sha(value) for key, value in files.items()},
            "run_config_hashes": [{
                "batch": "batch", "id": self.run_id, "problem_id": "q",
                "condition": "aprs", "sha256": self.config_hash,
            }],
        }
        data = encoded(index)
        (self.root / "archive-index.json").write_bytes(data)
        self.anchor.update(index_sha256=sha(data), files=len(files))

    def test_verifies_sources_and_bytes_without_restricted_key(self):
        self.write_bundle()
        self.assertEqual(check_archive(self.root, self.anchor, self.revision), {"files": 2, "runs": 1})

    def test_detects_trace_tampering(self):
        self.write_bundle()
        (self.root / self.trace_path).write_bytes(b"not the original")
        with self.assertRaisesRegex(EvidenceError, "digest mismatch"):
            check_archive(self.root, self.anchor, self.revision)

    def test_refuses_missing_trace_from_consistent_index(self):
        self.write_bundle(with_trace=False)
        with self.assertRaisesRegex(EvidenceError, "trace missing"):
            check_archive(self.root, self.anchor, self.revision)

    def test_recomputes_config_even_when_index_and_file_hash_agree(self):
        self.write_bundle(config={"scope": "配对", "cap": 12})
        with self.assertRaisesRegex(EvidenceError, "configuration mismatch"):
            check_archive(self.root, self.anchor, self.revision)

    def test_refuses_replaced_index(self):
        self.write_bundle()
        with (self.root / "archive-index.json").open("ab") as index:
            index.write(b"\n")
        with self.assertRaisesRegex(EvidenceError, "index digest mismatch"):
            check_archive(self.root, self.anchor, self.revision)
