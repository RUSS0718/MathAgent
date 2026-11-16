"""Repair provenance through a natural-input public Job, without outbound sockets."""
import json
import os
import socket
import sqlite3
import unittest
from contextlib import closing
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import ACCEPT, StarJobFixture
from tests.test_cp04_public_faults import checkpoint, CHALLENGE
from tests.test_faithful_s03_job import SPEC, CAPACITY_POLICY, ENDPOINT


class CheckpointRepairSourceTest(StarJobFixture, unittest.TestCase):
    def test_natural_round_limit_keeps_repaired_source(self):
        self.run_repair(continuation=False)

    def test_challenge_repair_source_allows_next_checkpoint_and_delivery(self):
        self.run_repair(continuation=True)

    def run_repair(self, *, continuation):
        if continuation:
            self.enterContext(patch("showcase.solver_harness.reasoner_checkpoint.MAX_CHECKPOINT_ROUNDS", 3))
        self.enterContext(patch.object(socket.socket, "connect", side_effect=AssertionError("outbound forbidden")))
        self.enterContext(patch.dict(os.environ, {"INTERN_API_BASE": ENDPOINT}))
        problem = "Evaluate 2+2, then explain the evaluated value."
        spec = deepcopy(SPEC)
        spec.update(original_problem=problem, root_obligations=[
            {"obligation_id": "value", "obligation_type": "existence", "statement": "Evaluate 2+2"},
            {"obligation_id": "explanation", "obligation_type": "format", "statement": "Explain the value",
             "prerequisite_ids": ["value"]}])
        plan = {"version": 1, "steps": [
            {"step_id": "evaluate", "title": "Evaluate", "objective": "Evaluate 2+2",
             "obligation_ids": ["value"], "auxiliary_goal_ids": [], "method_id": "direct"},
            {"step_id": "explain", "title": "Explain", "objective": "Explain the value",
             "obligation_ids": ["explanation"], "auxiliary_goal_ids": [], "depends_on": ["evaluate"], "method_id": "direct"}]}
        def draft(ctx, text, status="FINAL"):
            return checkpoint(ctx, text, status=status, claims=[{"statement": "2+2=4", "label": "hard-verify"}])
        def invalid(ctx):
            reply = draft(ctx, "Four follows from addition")
            reply["checkpoint"]["next_action"] = ""
            return reply
        def accepted(ctx):
            owner = ctx["step"]["obligation_ids"][0]
            return {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": "",
                    "obligation_evidence": [{"obligation_id": owner, "evidence_category": "existence_proof" if owner == "value" else "format_check", "claim_indexes": [0]}],
                    "classified_outcomes": [{"category": "Answer", "statement": "2+2=4",
                                             "scope": "integer addition", "claim_indexes": [0]}]}
        self.open_star([spec, plan, lambda c: draft(c, "Initial addition draft", "YIELD"), CHALLENGE,
                       invalid, lambda c: draft(c, "Repaired addition draft", "YIELD"), accepted,
                       lambda c: draft(c, "Completed addition argument"), accepted,
                       lambda c: draft(c, "Explanation by integer addition"), accepted,
                       {"final_response": "2+2=4 by integer addition."}, ACCEPT],
            stream_chunk_size=4096,
            SHOWCASE_STAR_ROUTING_POLICY_VERSION="objective-dependency-routing-v1",
            SHOWCASE_STAR_CONTEXT_CAPACITY=CAPACITY_POLICY,
            SHOWCASE_STAR_FEATURES=dict.fromkeys({"adaptive_solving", "auto_problem_spec", "problem_spec",
                "final_generation", "final_solution_review", "context_pack", "progress_scheduling",
                "reasoner_checkpoints", "proof_graph", "serial_routes"}, True),
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=20, max_http_attempts=20, max_tool_calls=0))
        response = self.client.post("/api/agent/jobs", headers=self.headers(), json={
            "message": problem, "session_id": self.session, "solver_mode": "star_limited"})
        self.assertEqual(202, response.status_code)
        job_id = response.get_json()["job_id"]
        final = self.terminal(job_id)
        with closing(sqlite3.connect(Path(self.data_dir) / "showcase.sqlite3")) as db:
            state = json.loads(db.execute("SELECT state_json FROM solver_states").fetchone()[0])
        repairs = [c for c in state["calls"].values() if c["call_id"].endswith(":repair-1")]
        self.assertEqual(1, len(repairs), final)
        repair = repairs[0]
        self.assertEqual("completed", repair["status"])
        original = state["calls"][repair["call_id"].removesuffix(":repair-1")]
        self.assertEqual("protocol_failed", original["status"])
        repaired_cp = state["reasoner_checkpoints"][1]
        mismatches = [r for s in state["proof_graph"]["snapshots"] for r in s["not_imported_records"]
                      if r.get("reason") == "review_record_mismatch"]
        self.assertEqual(repair["call_id"], repaired_cp["call_id"],
                         {"status": final["status"], "reason": final.get("result", {}).get("solver", {}).get("result_reason"),
                          "mismatches": mismatches, "requests": len(self.outbound)})
        self.assertEqual([], mismatches)
        if not continuation:
            self.assertEqual("failed", final["status"])
            self.assertEqual("reasoner_checkpoint_round_limit", final["result"]["solver"]["result_reason"])
            self.assertEqual(7, len(self.outbound))
            return
        self.assertTrue(any(c.get("parent_checkpoint_id") == repaired_cp["checkpoint_id"]
                            for c in self.outbound if c["role"] == "reasoner" and "repair_instruction" not in c), {"final": final["result"]["solver"].get("result_reason"), "roles": [(c["role"], c.get("parent_checkpoint_id")) for c in self.outbound]})
        self.assertEqual("succeeded", final["status"], final)
        self.assertEqual("accepted", self.report(job_id)["semantics"]["whole_review"])
        before = len(self.outbound)
        for path in (f"/api/agent/jobs/{job_id}", f"/api/runs/{job_id}",
                     f"/api/agent/jobs/{job_id}/report", f"/api/runs/{job_id}/evidence"):
            self.assertEqual(200, self.client.get(path).status_code)
        self.assertEqual(before, len(self.outbound))
        self.assertEqual(13, before)
        self.assertEqual(0, final["result"]["budget"]["unresolved_attempts"])



