"""Incremental Population Memory costs remain estimates or explicitly unknown."""

import unittest

from showcase.solver_harness.faithful_memory_cost import measure_population_memory_cost


class PayloadSizer:
    def __init__(self, fail=False):
        self.fail = fail

    def serialized_payload_size(self, request):
        if self.fail:
            raise ValueError("payload_size_unavailable")
        role_context = request.get("role_context", {})
        state = role_context.get("state", {})
        has_memory = "population_memory_advisory" in state
        return 403 if has_memory else 301


class FaithfulS10MemoryCostTest(unittest.TestCase):
    def request(self):
        return {
            "role": "step_verifier",
            "role_context": {"state": {"population_memory_advisory": {
                "authority": "advisory_only",
                "observations": [{"record_id": "record-1", "content": {"route_id": "historic"}}],
            }}},
        }

    def test_cost_is_audited_as_incremental_estimate_without_storing_payload(self):
        cost = measure_population_memory_cost(
            PayloadSizer(), self.request(), input_fingerprint="a" * 64
        )

        self.assertEqual("estimated", cost["status"])
        self.assertEqual(["record-1"], cost["record_ids"])
        self.assertEqual(102, cost["additional_utf8_bytes"])
        self.assertEqual(34, cost["estimated_tokens"])
        self.assertIn("estimated", cost["estimator_version"])
        self.assertEqual("a" * 64, cost["input_fingerprint"])
        self.assertNotIn("historic", str(cost))

    def test_unmeasurable_cost_is_unknown_and_never_zero(self):
        cost = measure_population_memory_cost(
            PayloadSizer(fail=True), self.request(), input_fingerprint="b" * 64
        )

        self.assertEqual("unknown", cost["status"])
        self.assertIsNone(cost["additional_utf8_bytes"])
        self.assertIsNone(cost["estimated_tokens"])


if __name__ == "__main__":
    unittest.main()
