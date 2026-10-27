"""Independent #97 registration checks with a self-contained synthetic draft."""

import copy
import hashlib
import unittest
from unittest.mock import patch

from showcase import star_readiness_registration
from showcase.star_readiness_registration import (
    ADAPTER_VERSION,
    adapt_draft,
    digest,
    registration,
)

SIMPLE_TEXT = "Synthetic fixture A: compute 17 + 25."
MULTI_TEXT = "Synthetic fixture B: sum the first five positive integers."
SIMPLE_HASH = hashlib.sha256(SIMPLE_TEXT.encode("utf-8")).hexdigest()
MULTI_HASH = hashlib.sha256(MULTI_TEXT.encode("utf-8")).hexdigest()
TEST_QUESTION_SPECS = (
    ("simple-01", "https://example.invalid/simple", "simple_fastpath", SIMPLE_HASH),
    ("multi-01", "https://example.invalid/multi", "public_multistep", MULTI_HASH),
)
PRODUCTION_QUESTION_SPECS = star_readiness_registration.QUESTION_SPECS
QUESTIONS = [
    {
        "id": "simple-01",
        "prompt_sha256": SIMPLE_HASH,
        "source": "https://example.invalid/simple",
        "text": SIMPLE_TEXT,
        "type": "simple_fastpath",
    },
    {
        "id": "multi-01",
        "prompt_sha256": MULTI_HASH,
        "source": "https://example.invalid/multi",
        "text": MULTI_TEXT,
        "type": "public_multistep",
    },
]
MODEL = {
    "max_output_tokens": 8192,
    "name": "intern-s2",
    "request_timeout_seconds": 180,
    "retry": 3,
    "solver_mode": "star_reference",
    "temperature": 0.2,
    "thinking_mode": True,
    "verification_mode": "auto",
}
ROUND_LIMITS = {
    "charged_tokens": 98304,
    "environment_preflights": 3,
    "http_attempts": 24,
    "logical_calls": 18,
    "problem_tool_calls": 4,
    "runs": 2,
    "tools_including_environment": 7,
    "wall_seconds": 900,
}
STOP_ON = [
    "unknown_transport",
    "incomplete_or_unresolved_usage",
    "failure",
    "cancel",
    "hard_limit",
    "source_or_config_change",
    "ledger_or_binding_defect",
]
REFERENCE_CONFIGURATION = {
    "isolation_image_id": "sha256:fc913659cd06c9164aacf32cb498b1cf0a6f4b1b8aff66f55f4cd9ff31673a2d",
    "preset": {
        "allowed_tools": ["polynomial_check", "python_math"],
        "features": {
            "final_generation": True,
            "final_solution_review": True,
            "local_code_tool": True,
            "meta_guidance": True,
            "persistent_sessions": True,
            "reexplore_after_replan": True,
            "skills": True,
            "star_routing": True,
            "stream_recovery": True,
        },
        "hint_mode": "none",
        "max_challenge_rounds": 5,
        "max_explore_rounds": 2,
        "max_final_solution_retries": 2,
        "max_replans": 3,
        "tool_timeout_seconds": 20,
    },
    "registered_tools": ["polynomial_check", "python_math"],
}
SOURCE = {
    "revision": "a" * 40,
    "source_sha256": "b" * 64,
    "dirty_status": True,
}


def synthetic_draft():
    return {
        "budget_status": "proposed_unapproved",
        "dirty_status": True,
        "enforcement": "not_implemented",
        "evidence_types": ["scripted", "fault_injection", "live", "replay"],
        "execution_authorized": False,
        "model": copy.deepcopy(MODEL),
        "original_batch": "unchanged_not_counted",
        "previous_draft_sha256": "c" * 64,
        "question_encoding": "UTF-8 exact text with LF separators, no trailing newline",
        "questions": copy.deepcopy(QUESTIONS),
        "round_limits": copy.deepcopy(ROUND_LIMITS),
        "runner_qualification": "not_implemented",
        "schedule": [
            {
                "attempts": 1,
                "limits": {
                    "charged_tokens": 32768,
                    "http_attempts": 8,
                    "logical_calls": 6,
                    "problem_tool_calls": 1,
                    "wall_seconds": 300,
                },
                "question": "simple-01",
                "transport": "nonstream",
            },
            {
                "attempts": 1,
                "limits": {
                    "charged_tokens": 65536,
                    "http_attempts": 16,
                    "logical_calls": 12,
                    "problem_tool_calls": 3,
                    "wall_seconds": 600,
                },
                "question": "multi-01",
                "transport": "nonstream",
            },
        ],
        "source_identity": {
            "revision": "d" * 40,
            "source_sha256": "e" * 64,
        },
        "status": "draft_not_dispatchable",
        "stop_on": copy.deepcopy(STOP_ON),
        "version": "issue-97-nonstream-draft-v2",
    }


class StarReadinessRegistrationTest(unittest.TestCase):
    def setUp(self):
        question_specs = patch(
            "showcase.star_readiness_registration.QUESTION_SPECS", TEST_QUESTION_SPECS
        )
        question_specs.start()
        self.addCleanup(question_specs.stop)

    def make_manifest(self, *, current_source=None):
        draft = synthetic_draft()
        return adapt_draft(
            draft,
            current_source=copy.deepcopy(SOURCE if current_source is None else current_source),
        )

    def test_production_specs_keep_confirmed_question_hashes(self):
        self.assertEqual(
            (
                (
                    "simple-01",
                    "https://projecteuler.net/problem=1",
                    "simple_fastpath",
                    "e84be303c2719dd77c917a0a6d75884a7c9abdd6f4c55e1069ff6af67a033cfb",
                ),
                (
                    "multi-01",
                    "https://projecteuler.net/problem=10",
                    "public_multistep",
                    "874c20406723e261e1f2dde0c5ab7f9ccb9e76957c48cb84718383151ccce5d6",
                ),
            ),
            PRODUCTION_QUESTION_SPECS,
        )

    def test_adapter_freezes_questions_model_source_budget_and_stop_conditions(self):
        manifest = self.make_manifest()

        self.assertEqual(ADAPTER_VERSION, manifest["adapter_version"])
        self.assertEqual("issue-97-nonstream-draft-v2", manifest["draft_version"])
        self.assertEqual("draft_not_dispatchable", manifest["status"])
        self.assertFalse(manifest["execution_authorized"])
        self.assertEqual("loopback_only", manifest["provider_mode"])
        self.assertEqual(
            [(q["id"], q["source"], q["text"], q["prompt_sha256"])
             for q in QUESTIONS],
            [(q["id"], q["source"], q["text"], q["text_sha256"])
             for q in manifest["questions"]],
        )
        self.assertEqual(["simple-01", "multi-01"], [s["question"] for s in manifest["schedule"]])
        self.assertEqual(["nonstream", "nonstream"], [s["transport"] for s in manifest["schedule"]])
        self.assertEqual([1, 1], [s["attempts"] for s in manifest["schedule"]])
        self.assertEqual(MODEL, manifest["model"])
        self.assertEqual(SOURCE, manifest["source_identity"])
        self.assertEqual(ROUND_LIMITS, manifest["round_limits"])
        self.assertEqual(STOP_ON, manifest["stop_on"])
        self.assertEqual(REFERENCE_CONFIGURATION, manifest["reference_configuration"])

    def test_isolation_image_matches_the_runtime_contract(self):
        from showcase.star_product_runtime import CONTRACT_PYTHON_IMAGE_ID

        manifest = self.make_manifest()

        self.assertEqual(
            CONTRACT_PYTHON_IMAGE_ID,
            manifest["reference_configuration"]["isolation_image_id"],
        )

    def test_registration_accepts_frozen_hash_and_matching_current_identity(self):
        manifest = self.make_manifest()

        loaded = registration(
            manifest,
            expected_sha256=digest(manifest),
            current_source=SOURCE,
        )

        self.assertEqual(manifest, loaded)
        self.assertIsNot(manifest, loaded)

    def test_registration_rejects_question_tampering_after_hashes_are_recomputed(self):
        manifest = self.make_manifest()
        manifest["questions"][0]["text"] += " changed"
        manifest["questions"][0]["text_sha256"] = hashlib.sha256(
            manifest["questions"][0]["text"].encode("utf-8")
        ).hexdigest()

        with self.assertRaises(ValueError):
            registration(manifest, expected_sha256=digest(manifest), current_source=SOURCE)

    def test_registration_rejects_reference_configuration_drift_after_rehash(self):
        manifest = self.make_manifest()
        manifest["reference_configuration"]["preset"]["features"][
            "final_solution_review"
        ] = False

        with self.assertRaises(ValueError):
            registration(manifest, expected_sha256=digest(manifest), current_source=SOURCE)

    def test_registration_rejects_budget_transport_attempt_and_extra_slot_changes(self):
        mutations = []

        changed_budget = self.make_manifest()
        changed_budget["round_limits"]["charged_tokens"] += 1
        mutations.append(changed_budget)

        changed_transport = self.make_manifest()
        changed_transport["schedule"][0]["transport"] = "stream"
        mutations.append(changed_transport)

        changed_attempts = self.make_manifest()
        changed_attempts["schedule"][1]["attempts"] = 2
        mutations.append(changed_attempts)

        extra_slot = self.make_manifest()
        extra_slot["schedule"].append(copy.deepcopy(extra_slot["schedule"][0]))
        mutations.append(extra_slot)

        for manifest in mutations:
            with self.subTest(manifest=manifest):
                with self.assertRaises(ValueError):
                    registration(manifest, expected_sha256=digest(manifest), current_source=SOURCE)

    def test_registration_rejects_authorization_and_current_source_drift(self):
        live = self.make_manifest()
        live["execution_authorized"] = True
        with self.assertRaises(ValueError):
            registration(live, expected_sha256=digest(live), current_source=SOURCE)

        manifest = self.make_manifest()
        changed_source = {**SOURCE, "revision": "f" * 40}
        with self.assertRaises(ValueError):
            registration(manifest, expected_sha256=digest(manifest), current_source=changed_source)

        changed_dirty_state = {**SOURCE, "dirty_status": False}
        with self.assertRaises(ValueError):
            registration(manifest, expected_sha256=digest(manifest), current_source=changed_dirty_state)

        malformed_source = {**SOURCE, "source_sha256": "invalid"}
        with self.assertRaises(ValueError):
            registration(manifest, expected_sha256=digest(manifest), current_source=malformed_source)

    def test_adapter_rejects_draft_escalation_and_bad_question_hash(self):
        authorized = synthetic_draft()
        authorized["execution_authorized"] = True
        with self.assertRaises(ValueError):
            adapt_draft(authorized, current_source=SOURCE)

        modified = synthetic_draft()
        modified["questions"][1]["text"] += " changed"
        modified["questions"][1]["prompt_sha256"] = hashlib.sha256(
            modified["questions"][1]["text"].encode("utf-8")
        ).hexdigest()
        with self.assertRaises(ValueError):
            adapt_draft(modified, current_source=SOURCE)

        over_budget = synthetic_draft()
        over_budget["round_limits"]["charged_tokens"] += 1
        with self.assertRaises(ValueError):
            adapt_draft(over_budget, current_source=SOURCE)


if __name__ == "__main__":
    unittest.main()
