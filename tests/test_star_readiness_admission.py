"""The confirmed #97 batch cannot dispatch beyond its remaining budget."""

import unittest

from showcase.star_readiness_admission import admit_next_run


class ReadinessAdmissionTest(unittest.TestCase):
    def setUp(self):
        self.used = {"logical_calls": 0, "http_attempts": 0, "problem_tool_calls": 0,
                     "charged_tokens": 0}
        self.limits = {"logical_calls": 12, "http_attempts": 16, "problem_tool_calls": 3,
                       "charged_tokens": 65536, "wall_seconds": 600}

    def test_full_envelope_fits_at_confirmed_boundaries(self):
        used = {"logical_calls": 6, "http_attempts": 8, "problem_tool_calls": 1,
                "charged_tokens": 32768}
        self.assertIsNone(admit_next_run(used, self.limits, remaining_seconds=600, preflights=2))

    def test_rejects_each_insufficient_batch_dimension_before_dispatch(self):
        for key, used in (("logical_calls", 7), ("http_attempts", 9),
                          ("problem_tool_calls", 2), ("charged_tokens", 32769)):
            with self.subTest(key=key):
                self.assertEqual(f"round_{key}_insufficient", admit_next_run(
                    {**self.used, key: used}, self.limits, remaining_seconds=600, preflights=1))

    def test_rejects_insufficient_time_and_preflight_capacity(self):
        self.assertEqual("round_wall_seconds_insufficient", admit_next_run(
            self.used, self.limits, remaining_seconds=599, preflights=1))
        self.assertEqual("environment_preflight_insufficient", admit_next_run(
            self.used, self.limits, remaining_seconds=600, preflights=3))

    def test_invalid_accounting_cannot_admit_next_run(self):
        for used, remaining in (({**self.used, "charged_tokens": None}, 600),
                                (self.used, float("nan"))):
            with self.subTest(used=used, remaining=remaining):
                self.assertEqual("round_budget_invalid", admit_next_run(
                    used, self.limits, remaining_seconds=remaining, preflights=1))


if __name__ == "__main__":
    unittest.main()
