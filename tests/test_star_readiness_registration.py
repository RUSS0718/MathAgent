"""Independent #97 registration checks with a self-contained synthetic draft."""

import copy
import hashlib
import unittest
from unittest.mock import patch

from showcase import star_readiness_registration
from showcase.star_readiness_registration import (
    ADAPTER_VERSION,
    DRAFT_VERSION,
    V2_DRAFT_VERSION,
    V3_DRAFT_VERSION,
    V4_DRAFT_VERSION,
    adapt_draft,
    authorize_live_registration,
    digest,
    registration,
)

SIMPLE_TEXT = "Synthetic fixture A: compute 17 + 25."
MULTI_TEXT = "Synthetic fixture B: sum the first five positive integers."
SIMPLE_HASH = hashlib.sha256(SIMPLE_TEXT.encode("utf-8")).hexdigest()
MULTI_HASH = hashlib.sha256(MULTI_TEXT.encode("utf-8")).hexdigest()
SIMPLE_02_TEXT = "Synthetic fixture C: compute 8 * 9."
MULTI_02_TEXT = "Synthetic fixture D: sum the squares of the first four positive integers."
SIMPLE_02_HASH = hashlib.sha256(SIMPLE_02_TEXT.encode("utf-8")).hexdigest()
MULTI_02_HASH = hashlib.sha256(MULTI_02_TEXT.encode("utf-8")).hexdigest()
V4_SIMPLE_TEXT = """The sum of the squares of the first ten natural numbers is,
1^2 + 2^2 + ... + 10^2 = 385.

The square of the sum of the first ten natural numbers is,
(1 + 2 + ... + 10)^2 = 55^2 = 3025.

Hence the difference between the sum of the squares of the first ten natural numbers and the square of the sum is 3025 - 385 = 2640.

Find the difference between the sum of the squares of the first one hundred natural numbers and the square of the sum."""
V4_MULTI_TEXT = """Shan-Yu and Mulan are playing a game. Let θ be an angle with 0° < θ < 180° known to both players. Initially, Shan-Yu makes a paper triangle T with measurements of his choice. Then, they repeatedly perform the following steps:
• If T has at least one angle measuring exactly θ, then the game stops and Mulan wins.
• Otherwise, Mulan chooses a point P on the perimeter of T, different from its three vertices. She then makes a straight cut from P to the opposite vertex of T, splitting it into two triangles.
• Shan-Yu discards one of the two triangles. The remaining triangle becomes the new T.
For which real values of θ can Mulan guarantee her victory in finitely many steps, no matter how Shan-Yu plays?"""
V4_SIMPLE_HASH = "1a85541f75ac9b29a651a77f6bc3793048f652870a9da54f879ccfed7ecb1035"
V4_MULTI_HASH = "c8956a092a8c6b6004beed40bb1a6646e2a792299db5400dedd11bbd6912a086"
TEST_QUESTION_SPECS = (
    ("simple-01", "https://example.invalid/simple", "simple_fastpath", SIMPLE_HASH),
    ("multi-01", "https://example.invalid/multi", "public_multistep", MULTI_HASH),
)
PRODUCTION_QUESTION_SPECS = star_readiness_registration.V2_QUESTION_SPECS
PRODUCTION_V3_QUESTION_SPECS = star_readiness_registration.V3_QUESTION_SPECS
PRODUCTION_V4_QUESTION_SPECS = star_readiness_registration.V4_QUESTION_SPECS
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
V3_QUESTIONS = [
    {
        "id": "simple-02",
        "prompt_sha256": SIMPLE_02_HASH,
        "source": "https://example.invalid/simple-v3",
        "text": SIMPLE_02_TEXT,
        "type": "simple_fastpath",
    },
    {
        "id": "multi-02",
        "prompt_sha256": MULTI_02_HASH,
        "source": "https://example.invalid/multi-v3",
        "text": MULTI_02_TEXT,
        "type": "public_multistep",
    },
]
TEST_V3_QUESTION_SPECS = tuple(
    (question["id"], question["source"], question["type"], question["prompt_sha256"])
    for question in V3_QUESTIONS
)
V4_QUESTIONS = [
    {
        "id": "simple-03",
        "prompt_sha256": hashlib.sha256(V4_SIMPLE_TEXT.encode("utf-8")).hexdigest(),
        "source": "https://projecteuler.net/problem=6",
        "text": V4_SIMPLE_TEXT,
        "type": "simple_fastpath",
    },
    {
        "id": "multi-03",
        "prompt_sha256": hashlib.sha256(V4_MULTI_TEXT.encode("utf-8")).hexdigest(),
        "source": "https://www.imo-official.org/assets/documents/problems/2026/2026_eng.pdf#page=2",
        "text": V4_MULTI_TEXT,
        "type": "public_multistep",
    },
]
TEST_V4_QUESTION_SPECS = tuple(
    (question["id"], question["source"], question["type"], question["prompt_sha256"])
    for question in V4_QUESTIONS
)
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


def synthetic_v3_draft():
    draft = synthetic_draft()
    draft["version"] = V3_DRAFT_VERSION
    draft["questions"] = copy.deepcopy(V3_QUESTIONS)
    draft["schedule"][0]["question"] = "simple-02"
    draft["schedule"][1]["question"] = "multi-02"
    return draft


def synthetic_v4_draft():
    draft = synthetic_draft()
    draft["version"] = V4_DRAFT_VERSION
    draft["questions"] = copy.deepcopy(V4_QUESTIONS)
    draft["schedule"][0]["question"] = "simple-03"
    draft["schedule"][1]["question"] = "multi-03"
    return draft


def consumed_v2_manifest():
    draft = synthetic_draft()
    return {
        "reference_configuration": copy.deepcopy(REFERENCE_CONFIGURATION),
        "adapter_version": "issue-97-registration-adapter-v2",
        "draft_sha256": digest(draft),
        "draft_version": V2_DRAFT_VERSION,
        "execution_authorized": False,
        "model": copy.deepcopy(MODEL),
        "provider_mode": "loopback_only",
        "questions": [
            {
                "id": question["id"],
                "source": question["source"],
                "text": question["text"],
                "text_sha256": question["prompt_sha256"],
                "type": question["type"],
            }
            for question in draft["questions"]
        ],
        "round_limits": copy.deepcopy(ROUND_LIMITS),
        "schedule": copy.deepcopy(draft["schedule"]),
        "schema_version": 1,
        "source_identity": copy.deepcopy(SOURCE),
        "status": "draft_not_dispatchable",
        "stop_on": copy.deepcopy(STOP_ON),
    }


class StarReadinessRegistrationTest(unittest.TestCase):
    def setUp(self):
        question_specs = patch(
            "showcase.star_readiness_registration.V2_QUESTION_SPECS", TEST_QUESTION_SPECS
        )
        question_specs.start()
        self.addCleanup(question_specs.stop)
        v3_question_specs = patch(
            "showcase.star_readiness_registration.V3_QUESTION_SPECS", TEST_V3_QUESTION_SPECS
        )
        v3_question_specs.start()
        self.addCleanup(v3_question_specs.stop)
        v4_question_specs = patch(
            "showcase.star_readiness_registration.V4_QUESTION_SPECS", TEST_V4_QUESTION_SPECS
        )
        v4_question_specs.start()
        self.addCleanup(v4_question_specs.stop)

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

    def test_v3_specs_pin_the_two_supplied_prompt_hashes(self):
        self.assertEqual(
            (
                (
                    "simple-02",
                    "https://projecteuler.net/problem=2",
                    "simple_fastpath",
                    "764d9d6e78508d59d2c66ea1d4358c25f6d01c559fe7e1090bd29c929330d042",
                ),
                (
                    "multi-02",
                    "https://www.imo-official.org/assets/documents/problems/2026/2026_eng.pdf#page=2",
                    "public_multistep",
                    "f62ac6626ffa36647845b0e9d338191a9171899eed8615c033657c1ddc57e5b5",
                ),
            ),
            PRODUCTION_V3_QUESTION_SPECS,
        )

    def test_v4_is_the_default_and_pins_exact_sources_and_prompt_hashes(self):
        self.assertEqual(V4_DRAFT_VERSION, DRAFT_VERSION)
        self.assertEqual(PRODUCTION_V4_QUESTION_SPECS, star_readiness_registration.QUESTION_SPECS)
        self.assertEqual(
            (
                (
                    "simple-03",
                    "https://projecteuler.net/problem=6",
                    "simple_fastpath",
                    V4_SIMPLE_HASH,
                ),
                (
                    "multi-03",
                    "https://www.imo-official.org/assets/documents/problems/2026/2026_eng.pdf#page=2",
                    "public_multistep",
                    V4_MULTI_HASH,
                ),
            ),
            PRODUCTION_V4_QUESTION_SPECS,
        )
        self.assertEqual(V4_SIMPLE_HASH, hashlib.sha256(V4_SIMPLE_TEXT.encode("utf-8")).hexdigest())
        self.assertEqual(V4_MULTI_HASH, hashlib.sha256(V4_MULTI_TEXT.encode("utf-8")).hexdigest())

    def test_v4_adapter_freezes_exact_questions_schedule_and_existing_hard_budgets(self):
        manifest = adapt_draft(synthetic_v4_draft(), current_source=SOURCE)

        self.assertEqual(V4_DRAFT_VERSION, manifest["draft_version"])
        self.assertEqual(
            [(q["id"], q["source"], q["text"], q["prompt_sha256"]) for q in V4_QUESTIONS],
            [(q["id"], q["source"], q["text"], q["text_sha256"]) for q in manifest["questions"]],
        )
        self.assertEqual(["simple-03", "multi-03"], [s["question"] for s in manifest["schedule"]])
        self.assertEqual([1, 1], [s["attempts"] for s in manifest["schedule"]])
        self.assertEqual(["nonstream", "nonstream"], [s["transport"] for s in manifest["schedule"]])
        self.assertEqual(
            [
                {
                    "charged_tokens": 32768,
                    "http_attempts": 8,
                    "logical_calls": 6,
                    "problem_tool_calls": 1,
                    "wall_seconds": 300,
                },
                {
                    "charged_tokens": 65536,
                    "http_attempts": 16,
                    "logical_calls": 12,
                    "problem_tool_calls": 3,
                    "wall_seconds": 600,
                },
            ],
            [s["limits"] for s in manifest["schedule"]],
        )
        self.assertEqual(ROUND_LIMITS, manifest["round_limits"])

    def test_v4_authorization_has_its_own_scope_and_can_be_consumed_once(self):
        loopback = adapt_draft(synthetic_v4_draft(), current_source=SOURCE)

        with self.assertRaisesRegex(ValueError, "live_authorization_required"):
            authorize_live_registration(
                loopback,
                expected_sha256=digest(loopback),
                current_source=SOURCE,
                explicit_authorization=False,
                authorization_date="2026-10-28",
            )

        authorized = authorize_live_registration(
            loopback,
            expected_sha256=digest(loopback),
            current_source=SOURCE,
            explicit_authorization=True,
            authorization_date="2026-10-28",
        )
        self.assertEqual("issue-97-two-question-nonstream-batch-v4", authorized["authorization_scope"])
        self.assertEqual(
            authorized,
            registration(authorized, expected_sha256=digest(authorized), current_source=SOURCE),
        )
        with self.assertRaisesRegex(ValueError, "live_authorization_invalid"):
            authorize_live_registration(
                authorized,
                expected_sha256=digest(authorized),
                current_source=SOURCE,
                explicit_authorization=True,
                authorization_date="2026-10-29",
            )

        wrong_scope = copy.deepcopy(authorized)
        wrong_scope["authorization_scope"] = "issue-97-two-question-nonstream-batch-v3"
        with self.assertRaises(ValueError):
            registration(wrong_scope, expected_sha256=digest(wrong_scope), current_source=SOURCE)

    def test_v3_adapter_freezes_new_questions_with_existing_nonstream_budgets(self):
        manifest = adapt_draft(synthetic_v3_draft(), current_source=SOURCE)

        self.assertEqual("issue-97-nonstream-draft-v3", manifest["draft_version"])
        self.assertEqual(
            [(q["id"], q["source"], q["text"], q["prompt_sha256"]) for q in V3_QUESTIONS],
            [(q["id"], q["source"], q["text"], q["text_sha256"]) for q in manifest["questions"]],
        )
        self.assertEqual(["simple-02", "multi-02"], [s["question"] for s in manifest["schedule"]])
        self.assertEqual([1, 1], [s["attempts"] for s in manifest["schedule"]])
        self.assertEqual(["nonstream", "nonstream"], [s["transport"] for s in manifest["schedule"]])
        self.assertEqual(
            [
                {
                    "charged_tokens": 32768,
                    "http_attempts": 8,
                    "logical_calls": 6,
                    "problem_tool_calls": 1,
                    "wall_seconds": 300,
                },
                {
                    "charged_tokens": 65536,
                    "http_attempts": 16,
                    "logical_calls": 12,
                    "problem_tool_calls": 3,
                    "wall_seconds": 600,
                },
            ],
            [s["limits"] for s in manifest["schedule"]],
        )
        self.assertEqual(ROUND_LIMITS, manifest["round_limits"])
        self.assertEqual(2, manifest["schema_version"])

    def test_v3_registration_and_authorization_scope_are_versioned(self):
        loopback = adapt_draft(synthetic_v3_draft(), current_source=SOURCE)
        loaded = registration(
            loopback,
            expected_sha256=digest(loopback),
            current_source=SOURCE,
        )
        self.assertEqual(loopback, loaded)

        authorized = authorize_live_registration(
            loopback,
            expected_sha256=digest(loopback),
            current_source=SOURCE,
            explicit_authorization=True,
            authorization_date="2026-10-28",
        )
        self.assertEqual(
            "issue-97-two-question-nonstream-batch-v3",
            authorized["authorization_scope"],
        )
        self.assertEqual(
            authorized,
            registration(
                authorized,
                expected_sha256=digest(authorized),
                current_source=SOURCE,
            ),
        )

    def test_v2_consumed_loopback_manifest_remains_valid_for_registration(self):
        manifest = consumed_v2_manifest()

        self.assertEqual("issue-97-nonstream-draft-v2", manifest["draft_version"])
        self.assertEqual(
            manifest,
            registration(
                manifest,
                expected_sha256=digest(manifest),
                current_source=SOURCE,
            ),
        )

    def test_v3_live_manifest_cannot_be_reauthorized_even_with_a_new_date(self):
        loopback = adapt_draft(synthetic_v3_draft(), current_source=SOURCE)
        authorized = authorize_live_registration(
            loopback,
            expected_sha256=digest(loopback),
            current_source=SOURCE,
            explicit_authorization=True,
            authorization_date="2026-10-28",
        )
        original = copy.deepcopy(authorized)

        for authorization_date in ("2026-10-28", "2026-10-29"):
            with self.subTest(authorization_date=authorization_date):
                with self.assertRaisesRegex(ValueError, "live_authorization_invalid"):
                    authorize_live_registration(
                        authorized,
                        expected_sha256=digest(authorized),
                        current_source=SOURCE,
                        explicit_authorization=True,
                        authorization_date=authorization_date,
                    )
                self.assertEqual(original, authorized)

    def test_v2_consumed_loopback_manifest_cannot_be_authorized_for_live(self):
        manifest = consumed_v2_manifest()

        with self.assertRaisesRegex(ValueError, "live_draft_version_invalid"):
            authorize_live_registration(
                manifest,
                expected_sha256=digest(manifest),
                current_source=SOURCE,
                explicit_authorization=True,
                authorization_date="2026-10-28",
            )

    def test_historical_v2_live_manifest_is_readable_but_cannot_be_reauthorized(self):
        manifest = self.make_manifest()
        manifest.update(
            authorization_date="2026-10-28",
            authorization_scope="issue-97-two-question-nonstream-batch",
            execution_authorized=True,
            provider_endpoint="https://chat.intern-ai.org.cn/api/v1/chat/completions",
            provider_mode="intern_s2_live",
            status="authorized_live",
        )
        # Pin a synthetic historical envelope without loading real experiment data.
        with patch.object(
            star_readiness_registration, "V2_LIVE_MANIFEST_SHA256", digest(manifest)
        ):
            self.assertEqual(
                manifest,
                registration(manifest, expected_sha256=digest(manifest), current_source=SOURCE),
            )
            with self.assertRaisesRegex(ValueError, "live_draft_version_invalid"):
                authorize_live_registration(
                    manifest,
                    expected_sha256=digest(manifest),
                    current_source=SOURCE,
                    explicit_authorization=True,
                    authorization_date="2026-10-29",
                )
            manifest["authorization_date"] = "2026-10-29"
            with self.assertRaisesRegex(ValueError, "live_draft_version_invalid"):
                registration(manifest, expected_sha256=digest(manifest), current_source=SOURCE)

    def test_live_authorization_rejects_malformed_loopback_envelopes(self):
        mutations = {
            "execution_authorized": True,
            "provider_mode": "intern_s2_live",
            "status": "authorized_live",
            "authorization_date": "2026-10-28",
            "authorization_scope": "issue-97-two-question-nonstream-batch-v3",
            "provider_endpoint": "https://chat.intern-ai.org.cn/api/v1/chat/completions",
        }
        for key, value in mutations.items():
            with self.subTest(field=key):
                manifest = adapt_draft(synthetic_v3_draft(), current_source=SOURCE)
                manifest[key] = value
                with self.assertRaisesRegex(ValueError, "registration_invalid"):
                    authorize_live_registration(
                        manifest,
                        expected_sha256=digest(manifest),
                        current_source=SOURCE,
                        explicit_authorization=True,
                        authorization_date="2026-10-28",
                    )

    def test_v3_adapter_rejects_question_and_schedule_drift(self):
        changed_hash = synthetic_v3_draft()
        changed_hash["questions"][0]["prompt_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            adapt_draft(changed_hash, current_source=SOURCE)

        changed_budget = synthetic_v3_draft()
        changed_budget["schedule"][1]["limits"]["charged_tokens"] += 1
        with self.assertRaises(ValueError):
            adapt_draft(changed_budget, current_source=SOURCE)

        changed_attempt = synthetic_v3_draft()
        changed_attempt["schedule"][0]["attempts"] = 2
        with self.assertRaises(ValueError):
            adapt_draft(changed_attempt, current_source=SOURCE)

        changed_transport = synthetic_v3_draft()
        changed_transport["schedule"][1]["transport"] = "stream"
        with self.assertRaises(ValueError):
            adapt_draft(changed_transport, current_source=SOURCE)

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

    def test_live_manifest_requires_explicit_authorization_and_pins_provider(self):
        loopback = adapt_draft(synthetic_v3_draft(), current_source=SOURCE)
        manifest = authorize_live_registration(
            loopback,
            expected_sha256=digest(loopback),
            current_source=SOURCE,
            explicit_authorization=True,
            authorization_date="2026-10-27",
        )

        self.assertTrue(manifest["execution_authorized"])
        self.assertEqual("intern_s2_live", manifest["provider_mode"])
        self.assertEqual("authorized_live", manifest["status"])
        self.assertEqual(
            "https://chat.intern-ai.org.cn/api/v1/chat/completions",
            manifest["provider_endpoint"],
        )
        self.assertEqual(
            manifest,
            registration(manifest, expected_sha256=digest(manifest), current_source=SOURCE),
        )

    def test_live_manifest_rejects_endpoint_drift_even_after_rehash(self):
        loopback = adapt_draft(synthetic_v3_draft(), current_source=SOURCE)
        manifest = authorize_live_registration(
            loopback,
            expected_sha256=digest(loopback),
            current_source=SOURCE,
            explicit_authorization=True,
            authorization_date="2026-10-27",
        )
        manifest["provider_endpoint"] = "https://attacker.example/v1/chat/completions"

        with self.assertRaises(ValueError):
            registration(manifest, expected_sha256=digest(manifest), current_source=SOURCE)

    def test_live_registration_requires_explicit_true_authorization(self):
        loopback = adapt_draft(synthetic_v3_draft(), current_source=SOURCE)

        with self.assertRaisesRegex(ValueError, "live_authorization_required"):
            authorize_live_registration(
                loopback,
                expected_sha256=digest(loopback),
                current_source=SOURCE,
                explicit_authorization=False,
                authorization_date="2026-10-27",
            )

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
