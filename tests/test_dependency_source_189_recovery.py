"""Checkpoint quota and persistent completed-ruling recovery at Harness seams."""

import copy
import tempfile
import unittest
from pathlib import Path

from showcase.solver_harness import ScriptedModelPort, ScriptedVerifierPort, SolverHarness
from showcase.star_product_recovery import resume_solver
from tests.test_solver_harness_reasoner_checkpoint import checkpoint

PLAN = {"version": 1, "steps": [
    {"step_id": "s1", "title": "Parent", "objective": "derive"},
    {"step_id": "s2", "title": "Child", "objective": "derive", "depends_on": ["s1"]}]}
ACCEPT = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": ""}
BAD = {**ACCEPT, "classified_outcomes": [{"category": "Lemma", "statement": "parent",
    "scope": "derive", "claim_indexes": [0], "receipt_ids": ["unavailable"]}]}
GOOD = {**ACCEPT, "classified_outcomes": [{"category": "Lemma", "statement": "parent",
    "scope": "derive", "claim_indexes": [0]}]}
CHILD = {**ACCEPT, "classified_outcomes": [{"category": "Lemma", "statement": "child",
    "scope": "derive", "claim_indexes": [0], "dependencies": ["s1"]}]}
CONFIG = {"features": {"proof_graph": True, "stream_recovery": True,
                       "reasoner_checkpoints": True}, "max_model_calls": 12}


class ExitWindow(BaseException):
    pass


class DependencySource189RecoveryTest(unittest.TestCase):
    def test_yield_and_final_share_one_reclassification_and_keep_old_rulings(self):
        model = ScriptedModelPort([checkpoint(marker="yield"),
            checkpoint("FINAL", marker="final"), checkpoint("FINAL", marker="child")])
        verifier = ScriptedVerifierPort([BAD, GOOD, BAD, CHILD])
        with SolverHarness(config=CONFIG, model_port=model, verifier_port=verifier) as harness:
            result = harness.solve("controlled", {"run_id": "checkpoint-quota", "plan": PLAN})
        state = result["state"]
        self.assertEqual("FINAL_GENERATE", state["phase"])
        self.assertEqual(1, len(state["dependency_reclassifications"]))
        self.assertEqual(4, len(verifier.requests))
        self.assertEqual(1, sum("reclassification_of" in r for r in verifier.requests))
        original = next(c for c in state["calls"].values() if c.get("response") == BAD)
        self.assertEqual(BAD, original["response"])
        rows = state["verified_results_ledger"]
        self.assertEqual(2, len(rows))
        self.assertEqual([rows[0]["result_id"]], rows[1]["dependencies"])

    def test_completed_reclassification_survives_restart_without_new_call(self):
        def crash(run, event):
            cid = event.get("call_id", "")
            if ":dependency-review:" in cid and event.get("outcome") == "completed":
                raise ExitWindow()

        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "isolated.sqlite3"
            with SolverHarness(database_path=db, config=CONFIG,
                    model_port=ScriptedModelPort([checkpoint("FINAL", marker="parent")]),
                    verifier_port=ScriptedVerifierPort([BAD, GOOD]), event_observer=crash) as harness:
                with self.assertRaises(ExitWindow):
                    harness.solve("controlled", {"run_id": "restart", "plan": PLAN})
                before = harness.get_run("restart")
            verifier = ScriptedVerifierPort([CHILD])
            with SolverHarness(database_path=db, config=CONFIG,
                    model_port=ScriptedModelPort([checkpoint("FINAL", marker="child")]),
                    verifier_port=verifier) as harness:
                result = resume_solver(harness, "controlled", "restart", None)
                after = harness.get_run("restart")
                self.assertEqual("FINAL_GENERATE", result["state"]["phase"])
                self.assertEqual(1, len(verifier.requests))
                self.assertEqual("s2", verifier.requests[0]["step"]["step_id"])
                self.assertEqual(1, len(after["state"]["dependency_reclassifications"]))
                self.assertEqual(before["state"]["counters"]["model_calls"] + 2,
                                 after["state"]["counters"]["model_calls"])
                for cid, call in before["state"]["calls"].items():
                    self.assertEqual(call, after["state"]["calls"][cid])

    def test_saved_ruling_does_not_bind_changed_spec_report_or_checkpoint(self):
        from showcase.solver_harness.dependency_reclassification import saved_review, scope_id

        state = {"run_id": "r", "plan_version": 1, "attempt_index": 0,
                 "specification_version": 1, "steps": {"s": {"report": {"claims": []},
                                                           "checkpoint_id": "cp"}}}
        key = scope_id(state, "s")
        state["dependency_reclassifications"] = {key: {"specification_version": 1,
            "report": {"claims": []}, "checkpoint_id": "cp"}}
        self.assertIsNotNone(saved_review(state, "s"))
        for variant in ("spec", "report", "checkpoint"):
            changed = copy.deepcopy(state)
            if variant == "spec":
                changed["specification_version"] = 2
            elif variant == "report":
                changed["steps"]["s"]["report"]["claims"] = [{"statement": "different"}]
            else:
                changed["steps"]["s"]["checkpoint_id"] = "next"
            self.assertIsNone(saved_review(changed, "s"))
            self.assertIn(key, changed["dependency_reclassifications"])

    def test_completed_accept_must_review_current_checkpoint(self):
        from showcase.solver_harness.dependency_reclassification import completed_accept

        identity = {"run_id": "r", "problem_hash": "p", "config_hash": "c",
                    "plan_version": 1, "attempt_index": 0}
        old, current = {"checkpoint_id": "old"}, {"checkpoint_id": "current"}
        report = {"claims": []}
        state = {**identity, "steps": {"s": {"report": report, "checkpoint_id": "current"}},
                 "reasoner_checkpoints": [old, current], "calls": {"v": {
                     **identity, "role": "step_verifier", "status": "completed",
                     "request": {"step": {"step_id": "s"}, "report": report, "checkpoint": old}}}}
        self.assertFalse(completed_accept(state, "v", "s", report, {**ACCEPT, "valid": True}))
        state["calls"]["v"]["request"]["checkpoint"] = current
        self.assertTrue(completed_accept(state, "v", "s", report, {**ACCEPT, "valid": True}))

    def test_revoked_checkpoint_result_does_not_renew_quota_or_support_child(self):
        def crash(run, event):
            if event.get("type") == "step_reviewed" and event.get("checkpoint_status") == "YIELD":
                raise ExitWindow()

        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "isolated.sqlite3"
            with SolverHarness(database_path=db, config=CONFIG,
                    model_port=ScriptedModelPort([checkpoint(marker="parent")]),
                    verifier_port=ScriptedVerifierPort([BAD, GOOD]), event_observer=crash) as harness:
                with self.assertRaises(ExitWindow):
                    harness.solve("controlled", {"run_id": "revoked", "plan": PLAN})
            verifier = ScriptedVerifierPort([BAD])
            with SolverHarness(database_path=db, config=CONFIG,
                    model_port=ScriptedModelPort([checkpoint("FINAL", marker="final")]),
                    verifier_port=verifier) as harness:
                run = harness.get_run("revoked")
                rows = [{**r, "invalidated": True, "valid": False}
                        for r in run["state"]["verified_results_ledger"]]
                harness.commit_event("revoked", expected_revision=run["state_revision"],
                    event={"event_id": "withdraw", "type": "controlled_source_withdrawal"},
                    state_updates={"verified_results_ledger": rows})
                result = resume_solver(harness, "controlled", "revoked", None)
            self.assertEqual("dependency_reclassification_failed", result["state"]["result_reason"])
            self.assertEqual(1, len(verifier.requests))
            self.assertFalse(any("reclassification_of" in r for r in verifier.requests))
            self.assertEqual(1, len(result["state"]["dependency_reclassifications"]))
