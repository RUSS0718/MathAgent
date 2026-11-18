"""Repair the observed checkpoint tool location without discarding a proposed tool."""

import json
import unittest

from showcase.solver_harness.intern_instructions import response_instructions
from showcase.solver_harness.intern_schemas import response_schema
from showcase.solver_harness.protocol_repair import repair_request
from showcase.solver_harness.reasoner_checkpoint import parse
from tests.test_solver_harness_reasoner_checkpoint import checkpoint


class CheckpointToolTest(unittest.TestCase):
    def test_misplaced_tool_stays_rejected_and_repair_explains_legal_location(self):
        tool = {"tool": "python_math", "arguments": {"code": "print(1+1)"},
                "scope": "finite_computation"}
        invalid = checkpoint()
        invalid["checkpoint"].update(tool_request=tool, tool_evidence_refs=[])
        with self.assertRaises(ValueError):
            parse(invalid)
        request = {"run_id": "r", "call_id": "c", "role": "reasoner", "checkpoint_protocol": True}
        repaired = repair_request(request, failed_call={
            **request, "request": request, "status": "protocol_failed",
            "error_category": "invalid_role_schema", "partial_text": json.dumps(invalid)})
        self.assertIn("checkpoint.claims", repaired["repair_instruction"])
        self.assertEqual(tool, json.loads(repaired["format_repair"]["previous_response"])["checkpoint"]["tool_request"])
        valid = checkpoint(tool_request=tool)
        self.assertEqual(tool, parse(valid)["claims"][0]["tool_request"])

    def test_reasoner_guidance_uses_claim_location_and_never_requests_a_verdict_field(self):
        request = {"role": "reasoner", "checkpoint_protocol": True}
        instructions = response_instructions(request, response_schema(request))
        self.assertIn("checkpoint.claims", instructions)
        self.assertNotIn("provisional enum verdict", instructions)
