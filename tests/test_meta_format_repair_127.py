"""Meta uses the existing single format-repair boundary for complete bad replies."""

import unittest

from showcase.solver_harness import SolverHarness
from showcase.solver_harness.intern_port import InternPortError

GUIDANCE = {"action_type": "retry_different_method", "specific_task": "derive the bound",
            "use_pure_reasoning": True, "trace_back_to": None, "rationale": "avoid computation"}


class MetaFormatRepairTest(unittest.TestCase):
    def run_meta(self, failures, category="invalid_role_schema"):
        class Port:
            def __init__(self):
                self.requests = []

            def complete(self, request):
                self.requests.append(request)
                if len(self.requests) <= failures:
                    error = InternPortError(category)
                    if category == "invalid_role_schema":
                        error.finish_reason = "stop"
                    raise error
                return GUIDANCE

        port = Port()
        with SolverHarness(config={"max_model_calls": 8, "features": {
            "star_routing": True, "stream_recovery": True,
        }}, meta_port=port) as harness:
            result = harness.solve("prove", {"run_id": "meta-format", "meta_guidance": {"failure_type": "stuck"}})
        return port, result

    def test_known_schema_failure_repairs_once_with_same_task_and_new_identity(self):
        port, result = self.run_meta(1)
        self.assertEqual(2, len(port.requests))
        self.assertTrue(port.requests[1]["call_id"].endswith(":repair-1"))
        self.assertEqual(port.requests[0]["guidance_request"], port.requests[1]["guidance_request"])
        self.assertEqual("STEP_EXECUTE", result["state"]["phase"])
        self.assertEqual(2, result["state"]["counters"]["model_calls"])
        self.assertEqual(GUIDANCE, {k: result["state"]["meta_guidance_decision"][k] for k in GUIDANCE})

    def test_second_schema_failure_and_unknown_transport_do_not_loop(self):
        for failures, category, expected in ((2, "invalid_role_schema", 2), (1, "tls", 1)):
            with self.subTest(category=category):
                port, result = self.run_meta(failures, category)
                self.assertEqual(expected, len(port.requests))
                self.assertIsNone(result["state"].get("meta_guidance_decision"))
