"""Versioned admission for the bounded v7 #97 run envelope."""

import unittest

from showcase import star_readiness_admission
from showcase.star_readiness_admission import (
    admit_next_run,
)
from showcase.star_readiness_registration import (
    V2_DRAFT_VERSION,
    V3_DRAFT_VERSION,
    V4_DRAFT_VERSION,
    V5_DRAFT_VERSION,
    V6_DRAFT_VERSION,
)
from showcase.star_readiness_v7 import (
    V7_DRAFT_VERSION,
    V7_ROUND_LIMITS,
    V7_RUN_LIMITS,
)


class StarReadinessV7AdmissionTest(unittest.TestCase):
    def setUp(self):
        self.used = {
            "logical_calls": 0,
            "http_attempts": 0,
            "problem_tool_calls": 0,
            "charged_tokens": 0,
        }
        self.v7_limits = {
            "logical_calls": 24,
            "http_attempts": 72,
            "problem_tool_calls": 8,
            "charged_tokens": 524288,
            "wall_seconds": 7200,
        }

    def test_admission_envelope_matches_registered_v7_limits(self):
        self.assertEqual(V7_RUN_LIMITS[0], self.v7_limits)
        self.assertEqual(V7_RUN_LIMITS, star_readiness_admission.V7_RUN_LIMITS)
        self.assertEqual(V7_ROUND_LIMITS, star_readiness_admission.V7_ROUND_LIMITS)
        self.assertEqual(7500, V7_ROUND_LIMITS["wall_seconds"])
        self.assertEqual(3, V7_ROUND_LIMITS["environment_preflights"])
        self.assertEqual(11, V7_ROUND_LIMITS["tools_including_environment"])

    def test_v7_admits_the_complete_envelope_at_each_exact_boundary(self):
        self.assertIsNone(admit_next_run(
            self.used,
            self.v7_limits,
            remaining_seconds=7500,
            preflights=2,
            registration_version=V7_DRAFT_VERSION,
        ))

        self.assertEqual(
            "round_runs_insufficient",
            admit_next_run(
                self.used,
                self.v7_limits,
                remaining_seconds=7500,
                preflights=2,
                runs=1,
                registration_version=V7_DRAFT_VERSION,
            ),
        )

    def test_v7_rejects_one_unit_over_each_cumulative_round_limit(self):
        for key in ("logical_calls", "http_attempts", "problem_tool_calls", "charged_tokens"):
            with self.subTest(key=key):
                self.assertEqual(
                    f"round_{key}_insufficient",
                    admit_next_run(
                        {**self.used, key: 1},
                        self.v7_limits,
                        remaining_seconds=4200,
                        preflights=0,
                        registration_version=V7_DRAFT_VERSION,
                    ),
                )

    def test_v7_rejects_run_wall_time_and_preflight_overages(self):
        oversized_run = {**self.v7_limits, "wall_seconds": 7201}
        self.assertEqual(
            "round_wall_seconds_insufficient",
            admit_next_run(
                self.used, oversized_run, remaining_seconds=7500, preflights=0,
                registration_version=V7_DRAFT_VERSION,
            ),
        )

        self.assertEqual(
            "round_wall_seconds_insufficient",
            admit_next_run(
                self.used, self.v7_limits, remaining_seconds=7199, preflights=0,
                registration_version=V7_DRAFT_VERSION,
            ),
        )
        self.assertEqual(
            "environment_preflight_insufficient",
            admit_next_run(
                self.used, {**self.v7_limits, "problem_tool_calls": 0},
                remaining_seconds=7500, preflights=3,
                registration_version=V7_DRAFT_VERSION,
            ),
        )

        self.assertEqual(
            "round_budget_invalid",
            admit_next_run(
                self.used, self.v7_limits, remaining_seconds=7501, preflights=0,
                registration_version=V7_DRAFT_VERSION,
            ),
        )

    def test_v7_accepts_exactly_eleven_combined_tools_and_rejects_twelve(self):
        self.assertIsNone(admit_next_run(
            self.used,
            self.v7_limits,
            remaining_seconds=7500,
            preflights=2,
            registration_version=V7_DRAFT_VERSION,
        ))
        self.assertEqual(
            "environment_tool_budget_insufficient",
            admit_next_run(
                self.used,
                self.v7_limits,
                remaining_seconds=7500,
                preflights=3,
                registration_version=V7_DRAFT_VERSION,
            ),
        )

    def test_historical_versions_still_admit_exactly_seven_combined_tools(self):
        for version in (
            V2_DRAFT_VERSION,
            V3_DRAFT_VERSION,
            V4_DRAFT_VERSION,
            V5_DRAFT_VERSION,
            V6_DRAFT_VERSION,
        ):
            with self.subTest(version=version):
                self.assertEqual(
                    None,
                    admit_next_run(
                        {**self.used, "problem_tool_calls": 4},
                        {
                            "logical_calls": 0,
                            "http_attempts": 0,
                            "problem_tool_calls": 0,
                            "charged_tokens": 0,
                            "wall_seconds": 600,
                        },
                        remaining_seconds=10000,
                        preflights=2,
                        registration_version=version,
                    ),
                )

    def test_v2_through_v6_keep_the_existing_admission_ceiling(self):
        for version in (
            V2_DRAFT_VERSION,
            V3_DRAFT_VERSION,
            V4_DRAFT_VERSION,
            V5_DRAFT_VERSION,
            V6_DRAFT_VERSION,
        ):
            with self.subTest(version=version):
                old_limits = {
                    "logical_calls": 12,
                    "http_attempts": 16,
                    "problem_tool_calls": 3,
                    "charged_tokens": 98305,
                    "wall_seconds": 600,
                }
                self.assertEqual(
                    "round_charged_tokens_insufficient",
                    admit_next_run(
                        self.used, old_limits, remaining_seconds=4200, preflights=0,
                        registration_version=version,
                    ),
                )

    def test_v2_through_v6_still_admit_within_the_historical_ceiling(self):
        old_limits = {
            "logical_calls": 12,
            "http_attempts": 16,
            "problem_tool_calls": 3,
            "charged_tokens": 65536,
            "wall_seconds": 600,
        }
        for version in (
            V2_DRAFT_VERSION,
            V3_DRAFT_VERSION,
            V4_DRAFT_VERSION,
            V5_DRAFT_VERSION,
            V6_DRAFT_VERSION,
        ):
            with self.subTest(version=version):
                self.assertIsNone(admit_next_run(
                    self.used, old_limits, remaining_seconds=4200, preflights=0,
                    registration_version=version,
                ))


if __name__ == "__main__":
    unittest.main()
