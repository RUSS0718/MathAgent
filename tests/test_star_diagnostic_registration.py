import copy
import json
import tempfile
import unittest
from pathlib import Path

from showcase.star_diagnostic_registration import digest, dry_run, freeze, validate
from tests.star_diagnostic_support import plan


class RegistrationTest(unittest.TestCase):
    def test_freeze_is_redacted_and_phase_limits_do_not_double_count(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = freeze(plan(), Path(directory) / "registration")
            report = dry_run(manifest)
            self.assertEqual(36, report["phase_limits"]["P"]["requests"])
            self.assertEqual(2359296, report["phase_limits"]["P"]["tokens"])
            self.assertEqual(900, manifest["requests"][0]["shadow_seconds"])
            self.assertNotIn("Give a complete proof", json.dumps(manifest))
            self.assertEqual(2, report["planned"])
            validate(manifest)

    def test_overlong_proof_is_rejected_without_truncation_or_registration(self):
        with tempfile.TemporaryDirectory() as directory:
            value = plan()
            proof = "proof" * 20000
            value["requests"][0]["prompt"] = proof
            target = Path(directory) / "registration"
            with self.assertRaisesRegex(ValueError, "too_long"):
                freeze(value, target)
            self.assertEqual(proof, value["requests"][0]["prompt"])
            self.assertFalse(target.exists())

    def test_resealed_manifest_cannot_raise_request_or_single_call_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = freeze(plan(), Path(directory) / "registration")
            manifest["requests"][0]["input_estimate"] = 49153
            manifest["sha256"] = digest({k: v for k, v in manifest.items() if k != "sha256"})
            with self.assertRaises(ValueError):
                validate(manifest)

    def test_all_stage_ceilings_and_conditional_not_started_are_explicit(self):
        expected = {"P": (36, 2359296, 32400, 36000), "O": (3, 196608, 5400, 7200),
                    "T": (24, 1572864, 32400, 36000), "T-3600": (4, 262144, 14400, 16200),
                    "R": (16, 1048576, 28800, 32400), "S": (8, 524288, 14400, 16200)}
        with tempfile.TemporaryDirectory() as directory:
            manifest = freeze(plan(), Path(directory) / "registration")
            limits = dry_run(manifest)["phase_limits"]
            for phase, values in expected.items():
                self.assertEqual(values, tuple(limits[phase][k] for k in ("requests", "tokens", "wait", "batch")))
            value = plan("S")
            value["conditions_met"] = False
            condition = freeze(value, Path(directory) / "conditional")
            self.assertEqual("not_started", dry_run(condition)["status"])

    def test_exact_65536_envelope_is_admitted_but_one_extra_byte_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            value = plan(count=1)
            value["requests"][0]["prompt"] = "x" * 48966
            manifest = freeze(value, Path(directory) / "exact")
            self.assertEqual(49152, manifest["requests"][0]["input_estimate"])
            self.assertEqual(dict(tokens=65536, logical=1, http=1, tools=0), manifest["single"])
            value["requests"][0]["prompt"] += "x"
            with self.assertRaisesRegex(ValueError, "too_long"):
                freeze(value, Path(directory) / "over")

    def test_frozen_fields_cannot_be_modified_and_source_must_match(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = freeze(plan(), Path(directory) / "registration")
            changes = {"upstream": "a" * 40, "seed": 42, "stop": [],
                       "parameters": {}, "source": {}, "window": {}, "requests": []}
            for key, value in changes.items():
                with self.subTest(key=key):
                    changed = copy.deepcopy(manifest)
                    changed[key] = value
                    with self.assertRaises(ValueError):
                        validate(changed)
            changed = copy.deepcopy(manifest)
            changed["source"]["sha"] = "0" * 40
            changed["sha256"] = digest({k: v for k, v in changed.items() if k != "sha256"})
            with self.assertRaisesRegex(ValueError, "source_changed"):
                validate(changed, check_source=True)

    def test_stage_request_count_and_wait_caps_cannot_be_exceeded(self):
        with tempfile.TemporaryDirectory() as directory:
            for value in (plan("O", 4), plan("T", 24)):
                with self.assertRaisesRegex(ValueError, "limit"):
                    freeze(value, Path(directory) / "invalid")
