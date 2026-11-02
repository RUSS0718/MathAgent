"""Exact, non-dispatchable v7 registration contract tests."""

import copy
import hashlib
import unittest
from unittest.mock import patch

from showcase import star_readiness_registration
from showcase.star_readiness_registration import (
    adapt_draft,
    authorize_live_registration,
    digest,
    registration,
)
from showcase.star_readiness_v7 import (
    V7_ADAPTER_VERSION,
    V7_AUTHORIZATION_SCOPE,
    V7_DRAFT_VERSION,
    V7_PREVIOUS_DRAFT_SHA256,
)

QUESTION_TEXT = "Synthetic fixture: establish a multistep olympiad result."
QUESTION_HASH = hashlib.sha256(QUESTION_TEXT.encode("utf-8")).hexdigest()
QUESTION_SPEC = (
    "multi-05",
    "https://example.invalid/imo-2024-p3",
    "public_multistep",
    QUESTION_HASH,
)
SOURCE = {"revision": "a" * 40, "source_sha256": "b" * 64, "dirty_status": True}


def synthetic_v7_draft():
    return {
        "authorization_scope": V7_AUTHORIZATION_SCOPE,
        "budget_status": "proposed_unapproved",
        "dirty_status": True,
        "enforcement": "not_implemented",
        "evidence_types": ["scripted", "fault_injection", "live", "replay"],
        "execution_authorized": False,
        "model": copy.deepcopy(star_readiness_registration.V7_MODEL),
        "original_batch": "unchanged_not_counted",
        "previous_draft_sha256": V7_PREVIOUS_DRAFT_SHA256,
        "question_encoding": "UTF-8 exact text with LF separators, no trailing newline",
        "questions": [{
            "id": QUESTION_SPEC[0],
            "prompt_sha256": QUESTION_HASH,
            "source": QUESTION_SPEC[1],
            "text": QUESTION_TEXT,
            "type": QUESTION_SPEC[2],
        }],
        "round_limits": copy.deepcopy(star_readiness_registration.V7_ROUND_LIMITS),
        "runner_qualification": "not_implemented",
        "schedule": [{
            "attempts": 1,
            "limits": copy.deepcopy(star_readiness_registration.V7_RUN_LIMITS[0]),
            "question": QUESTION_SPEC[0],
            "transport": "nonstream",
        }],
        "source_identity": {"revision": "c" * 40, "source_sha256": "d" * 64},
        "status": "draft_not_dispatchable",
        "stop_on": copy.deepcopy(star_readiness_registration.STOP_ON),
        "version": V7_DRAFT_VERSION,
    }


class StarReadinessV7RegistrationTest(unittest.TestCase):
    def setUp(self):
        self.specs = patch.object(star_readiness_registration, "V7_QUESTION_SPECS", (QUESTION_SPEC,))
        self.specs.start()
        self.addCleanup(self.specs.stop)

    def test_v7_spec_reuses_the_unconsumed_multi_step_sample(self):
        self.specs.stop()
        self.addCleanup(self.specs.start)

        self.assertEqual(
            (
                "multi-05",
                "https://www.imo-official.org/assets/documents/problems/2024/2024_eng.pdf#page=2",
                "public_multistep",
                "ef159e27e553a719f4cd411de7eef28ece951b3c1a332f8f9ddb56f4f64f64b4",
            ),
            star_readiness_registration.V7_QUESTION_SPECS[0],
        )

    def test_preview_freezes_exact_v7_envelope_and_remains_non_dispatchable(self):
        manifest = adapt_draft(synthetic_v7_draft(), current_source=SOURCE)

        self.assertEqual(V7_DRAFT_VERSION, manifest["draft_version"])
        self.assertEqual(V7_ADAPTER_VERSION, manifest["adapter_version"])
        self.assertEqual(["multi-05"], [item["id"] for item in manifest["questions"]])
        self.assertEqual(QUESTION_HASH, manifest["questions"][0]["text_sha256"])
        self.assertEqual(star_readiness_registration.V7_MODEL, manifest["model"])
        self.assertEqual(16384, manifest["model"]["max_output_tokens"])
        self.assertEqual(900, manifest["model"]["request_timeout_seconds"])
        self.assertEqual(star_readiness_registration.V7_RUN_LIMITS[0], manifest["schedule"][0]["limits"])
        self.assertEqual(star_readiness_registration.V7_ROUND_LIMITS, manifest["round_limits"])
        self.assertEqual(
            star_readiness_registration.STAR_REFERENCE_CONFIGURATION,
            manifest["reference_configuration"],
        )
        self.assertEqual("loopback_only", manifest["provider_mode"])
        self.assertIsNone(manifest["provider_endpoint"])
        self.assertIsNone(manifest["authorization_scope"])
        self.assertFalse(manifest["execution_authorized"])
        self.assertEqual("draft_not_dispatchable", manifest["status"])

    def test_draft_rejects_scope_previous_hash_question_and_budget_drift(self):
        mutations = []

        wrong_scope = synthetic_v7_draft()
        wrong_scope["authorization_scope"] = "issue-97-unregistered-scope"
        mutations.append(wrong_scope)

        wrong_previous_hash = synthetic_v7_draft()
        wrong_previous_hash["previous_draft_sha256"] = "0" * 64
        mutations.append(wrong_previous_hash)

        wrong_question = synthetic_v7_draft()
        wrong_question["questions"][0]["id"] = "multi-04"
        mutations.append(wrong_question)

        wrong_run_budget = synthetic_v7_draft()
        wrong_run_budget["schedule"][0]["limits"]["problem_tool_calls"] += 1
        mutations.append(wrong_run_budget)

        wrong_round_budget = synthetic_v7_draft()
        wrong_round_budget["round_limits"]["charged_tokens"] += 1
        mutations.append(wrong_round_budget)

        for draft in mutations:
            with self.subTest(draft=draft):
                with self.assertRaisesRegex(ValueError, "registration_invalid"):
                    adapt_draft(draft, current_source=SOURCE)

    def test_preview_registration_binds_adapter_version_and_full_hash(self):
        manifest = adapt_draft(synthetic_v7_draft(), current_source=SOURCE)
        frozen_hash = digest(manifest)

        self.assertEqual(
            manifest,
            registration(manifest, expected_sha256=frozen_hash, current_source=SOURCE),
        )

        wrong_version = copy.deepcopy(manifest)
        wrong_version["adapter_version"] = star_readiness_registration.ADAPTER_VERSION
        with self.assertRaisesRegex(ValueError, "registration_invalid"):
            registration(wrong_version, expected_sha256=digest(wrong_version), current_source=SOURCE)

        with self.assertRaisesRegex(ValueError, "identity_mismatch"):
            registration(manifest, expected_sha256="0" * 64, current_source=SOURCE)

    def test_live_scope_is_versioned_and_scope_tampering_is_rejected(self):
        preview = adapt_draft(synthetic_v7_draft(), current_source=SOURCE)
        authorized = authorize_live_registration(
            preview,
            expected_sha256=digest(preview),
            current_source=SOURCE,
            explicit_authorization=True,
            authorization_date="2026-10-28",
        )

        self.assertEqual(V7_AUTHORIZATION_SCOPE, authorized["authorization_scope"])
        self.assertTrue(authorized["execution_authorized"])
        self.assertEqual(
            authorized,
            registration(authorized, expected_sha256=digest(authorized), current_source=SOURCE),
        )

        tampered_scope = copy.deepcopy(authorized)
        tampered_scope["authorization_scope"] = "issue-97-single-question-nonstream-batch-v6"
        with self.assertRaisesRegex(ValueError, "registration_invalid"):
            registration(tampered_scope, expected_sha256=digest(tampered_scope), current_source=SOURCE)


if __name__ == "__main__":
    unittest.main()
