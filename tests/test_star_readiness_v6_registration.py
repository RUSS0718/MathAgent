"""Single-sample v6 registrations stay exact and non-dispatchable by default."""

import copy
import hashlib
import unittest
from unittest.mock import patch

from showcase import star_readiness_registration
from showcase.star_readiness_registration import (
    V6_DRAFT_VERSION,
    adapt_draft,
    authorize_live_registration,
    digest,
    registration,
)
from showcase.star_readiness_v6 import V6_PREVIOUS_DRAFT_SHA256

QUESTION_TEXT = "Synthetic fixture: prove one parity subsequence is periodic."
QUESTION_HASH = hashlib.sha256(QUESTION_TEXT.encode("utf-8")).hexdigest()
QUESTION_SPEC = (
    "multi-05",
    "https://example.invalid/imo-2024-p3",
    "public_multistep",
    QUESTION_HASH,
)
SOURCE = {"revision": "a" * 40, "source_sha256": "b" * 64, "dirty_status": True}


def synthetic_v6_draft():
    return {
        "budget_status": "proposed_unapproved",
        "dirty_status": True,
        "enforcement": "not_implemented",
        "evidence_types": ["scripted", "fault_injection", "live", "replay"],
        "execution_authorized": False,
        "model": copy.deepcopy(star_readiness_registration.V6_MODEL),
        "original_batch": "unchanged_not_counted",
        "previous_draft_sha256": V6_PREVIOUS_DRAFT_SHA256,
        "question_encoding": "UTF-8 exact text with LF separators, no trailing newline",
        "questions": [{
            "id": QUESTION_SPEC[0],
            "prompt_sha256": QUESTION_HASH,
            "source": QUESTION_SPEC[1],
            "text": QUESTION_TEXT,
            "type": QUESTION_SPEC[2],
        }],
        "round_limits": copy.deepcopy(star_readiness_registration.V6_ROUND_LIMITS),
        "runner_qualification": "not_implemented",
        "schedule": [{
            "attempts": 1,
            "limits": copy.deepcopy(star_readiness_registration.V6_RUN_LIMITS[0]),
            "question": QUESTION_SPEC[0],
            "transport": "nonstream",
        }],
        "source_identity": {"revision": "c" * 40, "source_sha256": "d" * 64},
        "status": "draft_not_dispatchable",
        "stop_on": copy.deepcopy(star_readiness_registration.STOP_ON),
        "version": V6_DRAFT_VERSION,
    }


class StarReadinessV6RegistrationTest(unittest.TestCase):
    def setUp(self):
        self.specs = patch.object(star_readiness_registration, "V6_QUESTION_SPECS", (QUESTION_SPEC,))
        self.specs.start()
        self.addCleanup(self.specs.stop)

    def test_production_spec_pins_the_new_official_sample_identity(self):
        self.specs.stop()
        self.addCleanup(self.specs.start)
        self.assertEqual(
            (
                "multi-05",
                "https://www.imo-official.org/assets/documents/problems/2024/2024_eng.pdf#page=2",
                "public_multistep",
                "ef159e27e553a719f4cd411de7eef28ece951b3c1a332f8f9ddb56f4f64f64b4",
            ),
            star_readiness_registration.V6_QUESTION_SPECS[0],
        )

    def test_single_sample_freezes_exact_budget_without_live_dispatch(self):
        manifest = adapt_draft(synthetic_v6_draft(), current_source=SOURCE)

        self.assertEqual(V6_DRAFT_VERSION, manifest["draft_version"])
        self.assertEqual(["multi-05"], [item["id"] for item in manifest["questions"]])
        self.assertEqual(QUESTION_HASH, manifest["questions"][0]["text_sha256"])
        self.assertEqual(["multi-05"], [item["question"] for item in manifest["schedule"]])
        self.assertEqual(3600, manifest["schedule"][0]["limits"]["wall_seconds"])
        self.assertEqual(3900, manifest["round_limits"]["wall_seconds"])
        self.assertEqual(600, manifest["model"]["request_timeout_seconds"])
        self.assertEqual("loopback_only", manifest["provider_mode"])
        self.assertIsNone(manifest["provider_endpoint"])
        self.assertFalse(manifest["execution_authorized"])
        self.assertEqual("draft_not_dispatchable", manifest["status"])

    def test_authorization_is_versioned_and_registration_binds_exact_hash(self):
        preview = adapt_draft(synthetic_v6_draft(), current_source=SOURCE)
        authorized = authorize_live_registration(
            preview,
            expected_sha256=digest(preview),
            current_source=SOURCE,
            explicit_authorization=True,
            authorization_date="2026-10-28",
        )

        self.assertEqual(
            "issue-97-single-question-nonstream-batch-v6",
            authorized["authorization_scope"],
        )
        self.assertEqual(
            authorized,
            registration(authorized, expected_sha256=digest(authorized), current_source=SOURCE),
        )

    def test_question_identity_and_prompt_hash_are_required(self):
        for key, value in (("id", "multi-04"), ("prompt_sha256", "0" * 64)):
            with self.subTest(key=key):
                draft = synthetic_v6_draft()
                draft["questions"][0][key] = value
                with self.assertRaisesRegex(ValueError, "registration_invalid"):
                    adapt_draft(draft, current_source=SOURCE)


if __name__ == "__main__":
    unittest.main()
