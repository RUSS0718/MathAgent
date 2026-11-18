"""Computation continuations retain unique event identities across claim repair."""

import unittest

from showcase.solver_harness import (
    ScriptedModelPort,
    ScriptedToolPort,
    ScriptedVerifierPort,
    SolverHarness,
)
from tests.test_solver_harness_verifier_compute import ACCEPT, CONFIG, PLAN, PREMATURE, REPORT


class ComputeRepairIdentityTest(unittest.TestCase):
    def test_claim_repair_can_request_another_compute_without_event_collision(self):
        invalid = {
            **ACCEPT,
            "answer_claim": {
                "claim_index": 9,
                "both_directions_proved": True,
                "assumptions": [],
                "approach": "Check the sole claim",
            },
        }
        second = dict(PREMATURE)
        corrected = {**ACCEPT, "answer_claim": {**invalid["answer_claim"], "claim_index": 0}}
        verifier = ScriptedVerifierPort([PREMATURE, invalid, second, corrected])
        tool = ScriptedToolPort(
            [
                {"status": "success", "output": 2, "exit_code": 0},
                {"status": "success", "output": 2, "exit_code": 0},
            ]
        )
        with SolverHarness(
            config={**CONFIG, "features": {**CONFIG["features"], "star_routing": True}},
            model_port=ScriptedModelPort([REPORT]),
            verifier_port=verifier,
            tool_port=tool,
        ) as harness:
            result = harness.solve("2+2", {"plan": PLAN})
            self.assertEqual(4, len(verifier.requests))
            self.assertEqual(1, len(tool.requests))
            self.assertTrue(result["state"]["steps"]["s1"]["verification"]["valid"])
            events = [e for e in result["events"] if e["type"] == "step_review_dispatched"]
            self.assertEqual(len(events), len({e["event_id"] for e in events}))
            self.assertEqual(4, len({r["call_id"] for r in verifier.requests}))


if __name__ == "__main__":
    unittest.main()
