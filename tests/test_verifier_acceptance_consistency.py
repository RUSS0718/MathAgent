"""Contradictory frozen-scope reviews cannot start a proof repair loop."""

import json
import sqlite3
import unittest
from contextlib import closing
from copy import deepcopy
from pathlib import Path

import requests

from showcase.solver_harness.intern_schemas import response_schema
from showcase.tool_schemas import schema_error
from showcase.tools import ToolRegistry
from tests import test_faithful_protocol_handoff as handoff
from tests.star_product_support import ACCEPT, StarJobFixture
from tests.test_faithful_s03_job import REPLIES, SPEC
from tests.test_solver_harness_planner_checkpoint import checkpoint as planner_checkpoint
from tests.test_solver_harness_reasoner_checkpoint import checkpoint as reasoner_checkpoint

CLAIM = {"claim_index": 0, "both_directions_proved": False, "claim_type": "general_proof",
         "assumptions": [], "approach": "Integer addition"}
BAD = {**REPLIES[3], "answer_claim": CLAIM}
GOOD = {**BAD, "answer_claim": {**CLAIM, "both_directions_proved": True},
        "classified_outcomes": [{"category": "Lemma", "statement": "1+1=2",
                                 "scope": "integers", "claim_indexes": [0]}]}
TOOL = {"tool": "polynomial_check", "scope": "finite_computation", "arguments": {
    "schema_version": 1, "variable": "x", "coefficients": ["1", "-2"],
    "domain": {"kind": "real"}, "candidates": ["2"]}}


class AcceptanceSchemaTest(unittest.TestCase):
    def test_terminal_review_consistency_and_pending_tool_are_distinct(self):
        request = {"role": "step_verifier", "problem_spec": SPEC,
                   "population_memory_advisory": {"authority": "advisory_only",
                                                  "observations": [{"record_id": "obs"}]}}
        schema = response_schema(request)
        cases = [(BAD, False), (GOOD, True),
                 ({**BAD, "tool_request": TOOL}, True),
                 ({**BAD, "tool_request": None}, False),
                 ({**BAD, "answer_claim": {k: v for k, v in CLAIM.items()
                                            if k != "claim_type"}}, False),
                 ({**BAD, "answer_claim": {**CLAIM, "claim_type": "numerical_evaluation"}}, True),
                 ({**GOOD, "answer_claim": {**CLAIM, "both_directions_proved": 1}}, False),
                 ({**BAD, "verdict": "CHALLENGE", "goal_gate": "PARTIAL"}, True),
                 (REPLIES[3], True), ({**GOOD, "logic_gate": "FAIL"}, False)]
        for reply, valid in cases:
            with self.subTest(reply=reply):
                self.assertEqual(valid, schema_error(reply, schema) is None)
                with_memory = {**reply, "memory_decisions": [
                    {"record_id": "obs", "decision": "reject", "reason": "Unrelated"}]}
                self.assertEqual(valid, schema_error(with_memory, schema) is None)
        # Older unscoped reviews still reach the conservative falsification guard.
        legacy = {k: v for k, v in BAD.items() if k != "obligation_evidence"}
        self.assertIsNone(schema_error(legacy, response_schema({"role": "step_verifier"})))


class AcceptanceRepairJobTest(StarJobFixture, unittest.TestCase):
    open_faithful = handoff.FaithfulProtocolHandoffTest.open_faithful
    submit = handoff.FaithfulProtocolHandoffTest.submit

    def run_case(self, repair=GOOD, *, compute=False, calls=12, after_repair=()):
        plan = deepcopy(REPLIES[1])
        plan["steps"][0]["method_id"] = "direct"
        report = reasoner_checkpoint("FINAL")
        report["checkpoint"].update(objective="prove the value", argument="1+1=2",
                                    claims=deepcopy(REPLIES[2]["claims"]))
        registry = ToolRegistry()
        registry.register("polynomial_check", lambda arguments: 2)
        review_replies = [{**BAD, "tool_request": TOOL}, BAD] if compute else [BAD]
        self.open_faithful([SPEC, REPLIES[0],
            {"checkpoint": {**planner_checkpoint("FINAL"), "gaps": []}, "plan": plan},
            report, *review_replies, repair, *after_repair, REPLIES[4], ACCEPT],
            calls=calls, registry=registry)
        job_id = self.submit()
        final = self.terminal(job_id)
        reviewers = [r for r in self.outbound if r["role"] == "step_verifier"]
        return job_id, final, reviewers

    def assert_repaired_delivery(self, compute=False):
        job_id, final, reviewers = self.run_case(compute=compute)
        self.assertEqual("succeeded", final["status"])
        self.assertEqual(3 if compute else 2, len(reviewers))
        self.assertEqual(reviewers[-2]["call_id"] + ":repair-1", reviewers[-1]["call_id"])
        repair = reviewers[-1]
        self.assertEqual(BAD, json.loads(repair["format_repair"]["previous_response"]))
        self.assertIn("Re-evaluate", repair["repair_instruction"])
        self.assertNotIn("preserve the verdict", repair["repair_instruction"].lower())
        self.assertNotIn("researcher", [r["role"] for r in self.outbound])
        self.assertEqual(9 if compute else 8, len(self.outbound))
        self.assertEqual(len(self.outbound), final["result"]["budget"]["http_attempts"])
        with closing(sqlite3.connect(Path(self.data_dir) / "showcase.sqlite3")) as connection:
            state = json.loads(connection.execute(
                "SELECT state_json FROM solver_states WHERE run_id=?", (job_id,)).fetchone()[0])
        self.assertEqual([repair["call_id"]], [row["review_call_id"]
                         for row in state["verified_results_ledger"]])
        if compute:
            self.assertEqual(1, final["result"]["budget"]["tool_calls"])
            self.assertEqual(reviewers[-2]["report"]["tool_receipts"],
                             repair["report"]["tool_receipts"])
        before = len(self.outbound)
        self.job(job_id)
        self.assertEqual(before, len(self.outbound))

    def test_contradictory_initial_review_gets_one_metered_ruling(self):
        self.assert_repaired_delivery()

    def test_contradictory_compute_continuation_keeps_receipt_and_repairs_once(self):
        self.assert_repaired_delivery(compute=True)

    def test_second_contradiction_stops_without_falsification_or_acceptance(self):
        _, final, reviewers = self.run_case(repair=BAD)
        self.assertEqual("failed", final["status"])
        self.assertEqual(2, len(reviewers))
        self.assertEqual(6, len(self.outbound))
        self.assertNotIn("researcher", [r["role"] for r in self.outbound])

    def test_second_compute_contradiction_does_not_repair_again(self):
        _, final, reviewers = self.run_case(repair=BAD, compute=True)
        self.assertEqual("failed", final["status"])
        self.assertEqual(3, len(reviewers))
        self.assertEqual(7, len(self.outbound))
        self.assertNotIn("researcher", [r["role"] for r in self.outbound])

    def test_repair_respects_root_call_budget(self):
        _, final, reviewers = self.run_case(calls=5)
        self.assertEqual("failed", final["status"])
        self.assertEqual(1, len(reviewers))
        self.assertEqual(5, final["result"]["budget"]["http_attempts"])

    def test_unknown_repair_is_not_resent(self):
        _, final, reviewers = self.run_case(repair=requests.ReadTimeout("unknown review"))
        self.assertEqual("failed", final["status"])
        self.assertEqual(2, len(reviewers))
        self.assertEqual(1, len(final["result"]["solver"]["recovery"]["unknown_calls"]))
        self.assertEqual(6, len(self.outbound))

    def test_unknown_compute_repair_is_not_swallowed_as_the_prior_known_failure(self):
        job_id, final, reviewers = self.run_case(
            repair=requests.ReadTimeout("unknown computation review"), compute=True)
        self.assertEqual("failed", final["status"])
        self.assertEqual(3, len(reviewers))
        self.assertEqual(1, len(final["result"]["solver"]["recovery"]["unknown_calls"]))
        self.assertEqual(7, len(self.outbound))
        with closing(sqlite3.connect(Path(self.data_dir) / "showcase.sqlite3")) as connection:
            events = [json.loads(row[0]) for row in connection.execute(
                "SELECT event_json FROM solver_events WHERE run_id=?", (job_id,))]
        self.assertFalse(any(event["type"] == "step_reviewed" for event in events))

    def test_initial_repair_and_compute_continuation_share_one_allowance(self):
        _, final, reviewers = self.run_case(
            repair={**GOOD, "tool_request": TOOL}, after_repair=[BAD, GOOD])
        self.assertEqual("failed", final["status"])
        self.assertEqual(3, len(reviewers))
        self.assertEqual(7, len(self.outbound))
        self.assertFalse(any(r["call_id"].endswith(":tool-1:repair-1") for r in reviewers))


if __name__ == "__main__":
    unittest.main()
