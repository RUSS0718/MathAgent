"""Explicit external registration contract, using only synthetic data."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from showcase.star_experiment_registration import digest, registration
from tests.star_experiment_support import synthetic_registration


class ExperimentRegistrationTest(unittest.TestCase):
    def test_explicit_manifest_and_identity_are_required(self):
        with self.assertRaises(TypeError):
            registration()
        record = synthetic_registration()
        self.assertEqual(record, registration(record, expected_sha256=digest(record)))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"manifest.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            self.assertEqual(record, registration(path, expected_sha256=digest(record)))
        with self.assertRaises(ValueError):
            registration(record, expected_sha256="0"*64)

    def test_rejects_tampered_structure_even_with_matching_identity(self):
        for mutate in [lambda r:r.update(version="other"),
                       lambda r:r["schedule"][0]["limits"].update(max_tokens=999999),
                       lambda r:r["schedule"][1].update(transport="nonstream"),
                       lambda r:r["questions"]["short_a"].update(prompt="changed"),
                       lambda r:r["questions"]["short_a"].update(obligations=[]),
                       lambda r:r["independent_oracles"].pop("short_a")]:
            record=copy.deepcopy(synthetic_registration())
            mutate(record)
            with self.assertRaises(ValueError):
                registration(record, expected_sha256=digest(record))
