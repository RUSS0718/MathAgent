"""Compatible lifecycle facts for the user-facing projection."""
import unittest
from showcase.star_product_events import decision_fields


class LifecycleTests(unittest.TestCase):
    def test_lifecycle_is_categorical_bound_and_does_not_change_recovery_status(self):
        for raw, expected in [("dispatched", "running"), ("completed", "completed"),
                              ("provider_failed", "failed"), ("protocol_failed", "failed"),
                              ("unknown", "unknown")]:
            with self.subTest(status=raw):
                state = {"run_id": "run", "calls": {"private": {
                    "run_id": "run", "role": "planner", "status": raw,
                    "request": "PRIVATE PROMPT", "response": "PRIVATE RESPONSE"}}}
                result = decision_fields({"type": "call_audit", "call_id": "private"}, state)
                self.assertEqual(result["call_lifecycle"], expected)
                self.assertEqual(result["call_status"], "completed" if raw == "completed"
                                 else "failed" if raw == "protocol_failed" else "unknown")
                self.assertNotIn("PRIVATE", str(result))
                state["calls"]["private"]["run_id"] = "other"
                self.assertNotIn("call_lifecycle", decision_fields(
                    {"type": "call_audit", "call_id": "private"}, state))
