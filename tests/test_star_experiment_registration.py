"""Frozen public sources and independent oracle never enter solver questions."""

import unittest

from showcase.star_experiment_registration import oracle, registration


class ExperimentRegistrationTest(unittest.TestCase):
    def test_frozen_order_budgets_and_independent_oracles(self):
        record = registration()
        self.assertEqual(10, len(record["schedule"]))
        self.assertEqual([("multiply", "nonstream"), ("multiply", "stream"),
                          ("fractions", "nonstream"), ("fractions", "stream")],
                         [(r["question"], r["transport"]) for r in record["schedule"][:4]])
        self.assertEqual(["digit_cancel", "sharp", "partitions"] * 2,
                         [r["question"] for r in record["schedule"][4:]])
        self.assertEqual(96, sum(r["limits"]["max_model_calls"] for r in record["schedule"]))
        self.assertEqual(128, sum(r["limits"]["max_http_attempts"] for r in record["schedule"]))
        self.assertEqual(22, sum(r["limits"]["max_tool_calls"] for r in record["schedule"]))
        self.assertEqual(524288, sum(r["limits"]["max_tokens"] for r in record["schedule"]))
        self.assertEqual("391", oracle("multiply"))
        self.assertEqual("11/12", oracle("fractions"))
        self.assertEqual("100", oracle("digit_cancel"))
        self.assertEqual("190569291", oracle("partitions"))
        self.assertNotIn("190569291", record["questions"]["partitions"]["prompt"])
        self.assertNotIn("oracle", record["questions"]["sharp"]["prompt"])
