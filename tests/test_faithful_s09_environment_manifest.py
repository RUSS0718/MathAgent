"""Check that the pinned Lean build manifest identifies its exact source inputs."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FaithfulS09EnvironmentManifestTest(unittest.TestCase):
    def test_build_manifest_matches_pinned_inputs_and_source_hashes(self):
        build_dir = ROOT / "docker" / "lean"
        build_input = json.loads((build_dir / "build-input.json").read_text(encoding="utf-8"))
        manifest = json.loads((build_dir / "build-manifest.json").read_text(encoding="utf-8"))
        payload = {key: value for key, value in manifest.items()
                   if key != "build_manifest_sha256"}
        for name, expected_hash in build_input["source_files"].items():
            actual_hash = hashlib.sha256((build_dir / name).read_bytes()).hexdigest()
            self.assertEqual(expected_hash, actual_hash, name)
        self.assertEqual(build_input, payload)
        canonical = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        self.assertEqual(manifest["build_manifest_sha256"], hashlib.sha256(canonical).hexdigest())


if __name__ == "__main__":
    unittest.main()
