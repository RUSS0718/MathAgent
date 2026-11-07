"""Meta sees executed evidence even when a verifier did not copy it into a report."""

import json
import unittest
from copy import deepcopy

from showcase.solver_harness.context_injection import prepare_role_context
from showcase.solver_harness.intern_port import InternModelPort
from showcase.solver_harness.prompts import compose_request


def evidence_run():
    receipt = {"receipt_id": "computed", "run_id": "meta-evidence", "step_id": "step1",
               "plan_version": 1, "attempt_index": 0, "tool": "python_math",
               "executed": True, "status": "success", "exit_code": 0,
               "unknown_outcome": False, "output": "252", "input_ref": "input:1"}
    state = {"phase": "META_DECIDE", "plan_version": 1, "attempt_index": 0,
             "current_step": "step2", "counters": {"tool_calls": 1},
             "plan": {"steps": [{"step_id": "step1", "objective": "count valid colorings"},
                                {"step_id": "step2", "objective": "classify fixed points"}]},
             "steps": {"step1": {"status": "ACCEPTED", "report": {},
                                  "verification": {"valid": True, "verdict": "ACCEPT"}},
                       "step2": {"report": {}, "verification": {"objections": ["missing cases"]}}},
             "accepted_results": [], "verified_results_ledger": [
                 {"result_id": "count", "source": "step1", "statement": "252 valid colorings",
                  "valid": True, "evidence_level": "tool_verified"}],
             "tool_receipts": [receipt], "failure_records": [], "meta_interventions": []}
    return {"run_id": "meta-evidence", "state_revision": 9, "state": state}


class MetaEvidenceContextTest(unittest.TestCase):
    def test_actual_messages_carry_ledger_receipt_missing_from_step_report(self):
        run = evidence_run()
        before = deepcopy(run)
        request = compose_request(run, {"role": "meta", "problem": "color the octagon"})
        messages = InternModelPort(original_problem="color the octagon")._messages(request, {})
        projection = next(json.loads(m["content"])["state"] for m in messages
                          if m["role"] == "system" and '"kind": "projection"' in m["content"])
        self.assertEqual("252", projection["tool_receipts"][0]["output"])
        self.assertEqual("count", projection["verified_results_ledger"][0]["result_id"])
        self.assertEqual("classify fixed points", projection["plan"]["steps"][1]["objective"])
        self.assertEqual(["missing cases"], projection["steps"]["step2"]["verification"]["objections"])
        self.assertEqual([], request["allowed_tools"])
        self.assertEqual(before, run)

    def test_non_meta_projection_does_not_expand_and_invalid_results_stay_excluded(self):
        run = evidence_run()
        run["state"]["verified_results_ledger"].append({"result_id": "dead", "valid": False})
        meta = prepare_role_context(run, {"role": "meta"})["state"]
        self.assertEqual(["count"], [x["result_id"] for x in meta["verified_results_ledger"]])
        ordinary = prepare_role_context(run, {"role": "reasoner"})["state"]
        self.assertNotIn("tool_receipts", ordinary)
