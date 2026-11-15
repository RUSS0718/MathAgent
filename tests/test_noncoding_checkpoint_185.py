"""Pure reasoning keeps the checkpoint contract through the real provider seam."""

import json
import sqlite3
import unittest
from contextlib import closing
from copy import deepcopy
from pathlib import Path

from showcase.run_budget import RunBudgetLimits
from showcase.solver_harness.intern_schemas import response_schema
from showcase.tool_schemas import schema_error
from tests.star_product_support import ACCEPT, StarJobFixture
from tests.test_cp04_public_faults import FEATURES, checkpoint
from tests.test_star_product_guidance import GUIDANCE, PLAIN
from tests.test_star_product_tools import NEED_PLAN, PLAN, VERDICT


class NoncodingCheckpointTest(StarJobFixture, unittest.TestCase):
    def test_pure_checkpoint_schema_rejects_plain_report_and_binds_current_goal(self):
        request = {"role": "reason_noncoding", "checkpoint_protocol": True,
                   "current_goal": "Compute 1+1"}
        reply = checkpoint({"call_id": "pure", "step": PLAN["steps"][0]}, "1+1=2")
        self.assertIsNone(schema_error(reply, response_schema(request)))
        self.assertIsNotNone(schema_error(PLAIN, response_schema(request)))
        reply["checkpoint"]["objective"] = "another objective"
        self.assertIsNotNone(schema_error(reply, response_schema(request)))

    def test_legacy_pure_report_remains_valid_without_checkpoint_flag(self):
        self.assertIsNone(schema_error(PLAIN, response_schema({"role": "reason_noncoding"})))

    def run_pure_checkpoint(self, *, needs_repair=False, graph=False):
        def blocked(context):
            reply = checkpoint(context, "The first method is blocked", status="YIELD")
            reply["checkpoint"]["blocked"] = True
            return reply

        replies = [NEED_PLAN, PLAN, blocked, GUIDANCE]
        if needs_repair:
            replies.append(PLAIN)
        verdict = {**VERDICT, **({"classified_outcomes": [{
            "category": "Lemma", "statement": "1+1=2", "scope": "integer addition",
            "claim_indexes": [0]}]} if graph else {})}
        replies.extend([lambda ctx: checkpoint(ctx, "Addition gives 1+1=2", claims=[
            {"statement": "1+1=2", "label": "hard-verify"}]),
            verdict, {"final_response": "2"}, ACCEPT])
        self.open_star(replies, stream_chunk_size=4096,
                       SHOWCASE_STAR_FEATURES={**FEATURES, "meta_guidance": True, "skills": True,
                                              **({"proof_graph": True} if graph else {})},
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                           max_model_calls=12, max_http_attempts=12, max_tool_calls=0))
        job_id = self.create_job()
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"],
                         final.get("result", {}).get("solver", {}).get("result_reason"))
        pure = [r for r in self.outbound if r["role"] == "reason_noncoding"]
        self.assertEqual(2 if needs_repair else 1, len(pure))
        self.assertTrue(all(r["checkpoint_protocol"] for r in pure))
        self.assertTrue(all(r["allowed_tools"] == [] for r in pure))
        self.assertEqual(9 if needs_repair else 8, len(self.outbound))
        self.assertEqual(0, final["result"]["budget"]["tool_calls"])
        self.assertEqual(0, final["result"]["budget"]["unresolved_attempts"])
        report = self.report(job_id)
        self.assertEqual("accepted", report["semantics"]["whole_review"])
        self.assertEqual("same_artifact", report["semantics"]["binding"])
        self.assertEqual(["step_verifier", "final_generator", "whole_solution_verifier"],
                         [r["role"] for r in self.outbound[-3:]])
        before = len(self.outbound)
        self.job(job_id)
        self.report(job_id)
        self.assertEqual(before, len(self.outbound))
        return pure

    def test_guidance_switch_reaches_independent_review_with_pure_checkpoint(self):
        self.run_pure_checkpoint()

    def test_plain_pure_reply_uses_one_protocol_repair_before_review(self):
        first, repair = self.run_pure_checkpoint(needs_repair=True)
        self.assertEqual(first["call_id"] + ":repair-1", repair["call_id"])
        self.assertEqual(first["step"], repair["step"])
        self.assertIn("repair_instruction", repair)
        self.assertEqual(first["current_goal"], repair["current_goal"])

    def test_reviewed_pure_checkpoint_reaches_graph_with_original_identity_fences(self):
        from showcase.solver_harness.proof_graph_sources import importable_ledger_rows

        self.run_pure_checkpoint(graph=True)
        with closing(sqlite3.connect(Path(self.data_dir) / "showcase.sqlite3")) as connection:
            state = json.loads(connection.execute("SELECT state_json FROM solver_states").fetchone()[0])
        ledger = state["verified_results_ledger"]
        self.assertEqual(1, len(ledger))
        imported, rejected = importable_ledger_rows(state, ledger)
        self.assertEqual([], rejected)
        self.assertEqual(1, len(imported))
        snapshot = state["proof_graph"]["snapshots"][-1]
        self.assertEqual([], snapshot["not_imported_records"])
        self.assertTrue(any(row["status"] == "accepted" for row in snapshot["derivations"].values()))
        source_id = imported[0][1]["report_call_id"]
        self.assertEqual("reason_noncoding", state["calls"][source_id]["role"])
        review_id = ledger[0]["review_call_id"]
        for path, value in [
            (("calls", source_id, "role"), "researcher"),
            (("calls", source_id, "status"), "unknown_outcome"),
            (("calls", source_id, "config_hash"), "foreign"),
            (("calls", source_id, "run_id"), "foreign"),
            (("calls", source_id, "plan_version"), 99),
            (("calls", source_id, "attempt_index"), 99),
            (("calls", source_id, "response", "checkpoint", "argument"), "forged"),
            (("calls", review_id, "request", "report", "argument"), "forged"),
            (("calls", review_id, "status"), "unknown_outcome"),
        ]:
            with self.subTest(tampered=path):
                altered = deepcopy(state)
                target = altered
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                self.assertEqual([], importable_ledger_rows(altered, ledger)[0])
