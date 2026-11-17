"""Public transitions preserve OR premises without rewriting source history."""

import copy
import unittest

from showcase.solver_harness import ScriptedModelPort, ScriptedVerifierPort, SolverHarness
from tests.test_solver_harness_reasoner_checkpoint import checkpoint


class GraphSourceWithdrawal206Test(unittest.TestCase):
    def _run(self):
        first = checkpoint(marker="parent-1")
        second = checkpoint("FINAL", marker="parent-2")
        for reply in (first, second):
            reply["checkpoint"]["claims"][0]["statement"] = "parent result"
        child = checkpoint("FINAL", marker="child")
        child["checkpoint"]["dependencies"] = ["s1"]
        accept = {"goal_gate": "YES", "logic_gate": "PASS",
                  "verdict": "ACCEPT", "objection": ""}
        parent_review = {**accept, "classified_outcomes": [{
            "category": "Lemma", "statement": "parent result", "scope": "derive",
            "claim_indexes": [0]}]}
        child_review = {**accept, "classified_outcomes": [{
            "category": "Lemma", "statement": "child", "scope": "derive",
            "claim_indexes": [0], "dependencies": ["s1"]}]}
        harness = SolverHarness(config={"features": {"proof_graph": True,
            "reasoner_checkpoints": True, "stream_recovery": True}, "max_model_calls": 10},
            model_port=ScriptedModelPort([first, second, child]),
            verifier_port=ScriptedVerifierPort([parent_review, parent_review, child_review]))
        harness.__enter__()
        self.addCleanup(harness.__exit__, None, None, None)
        run = harness.solve("controlled", {"run_id": "withdrawal-206", "plan": {
            "version": 1, "steps": [
                {"step_id": "s1", "title": "Parent", "objective": "derive"},
                {"step_id": "s2", "title": "Child", "objective": "derive",
                 "depends_on": ["s1"]}]}})
        self.assertEqual("FINAL_GENERATE", run["state"]["phase"])
        return harness, harness.get_run(run["run_id"])

    def _withdraw(self, harness, run, victims):
        ledger = copy.deepcopy(run["state"]["verified_results_ledger"])
        for row in ledger:
            if row["result_id"] in victims:
                row.update(valid=False, invalidated=True)
        return harness.commit_event(run["run_id"], expected_revision=run["state_revision"],
            event={"event_id": f"withdraw-{run['state_revision']}",
                   "type": "controlled_source_change"},
            state_updates={"verified_results_ledger": ledger})

    def _child(self, run):
        snapshot = run["state"]["proof_graph"]["snapshots"][-1]
        child = next(row for row in snapshot["derivations"].values()
                     if row["result_id"].startswith("s2:"))
        return child, snapshot["propositions"][child["conclusion"]]

    def test_withdraw_either_support_then_last_support(self):
        for which in ("chosen", "alternative"):
            with self.subTest(which=which):
                harness, run = self._run()
                before = copy.deepcopy(run["state"])
                rows = before["verified_results_ledger"]
                selected = rows[2]["dependencies"][0]
                other = next(row["result_id"] for row in rows[:2]
                             if row["result_id"] != selected)
                victim, remaining = (selected, other) if which == "chosen" else (other, selected)
                run = self._withdraw(harness, run, {victim})
                child, prop = self._child(run)
                self.assertEqual("accepted", child["status"])
                self.assertEqual("supported", prop["status"])
                self.assertEqual(rows[2], run["state"]["verified_results_ledger"][2])
                self.assertEqual(before["calls"], run["state"]["calls"])
                self.assertEqual(before["proof_graph"]["snapshots"],
                    run["state"]["proof_graph"]["snapshots"][:len(before["proof_graph"]["snapshots"])])
                run = self._withdraw(harness, run, {remaining})
                child, prop = self._child(run)
                self.assertEqual("invalidated", child["status"])
                self.assertEqual("invalidated", prop["status"])

    def test_withdrawn_required_premise_or_child_cannot_resurrect(self):
        for target in ("parents", "child"):
            with self.subTest(target=target):
                harness, run = self._run()
                original = copy.deepcopy(run["state"]["verified_results_ledger"])
                victims = original[:2] if target == "parents" else original[2:]
                run = self._withdraw(harness, run, {row["result_id"] for row in victims})
                self.assertEqual("invalidated", self._child(run)[0]["status"])
                restored = harness.commit_event(run["run_id"],
                    expected_revision=run["state_revision"],
                    event={"event_id": "restore-flags", "type": "controlled_source_change"},
                    state_updates={"verified_results_ledger": original})
                self.assertEqual("invalidated", self._child(restored)[0]["status"])
                self.assertEqual("invalidated", self._child(restored)[1]["status"])

    def test_established_child_loses_all_invalid_or_cross_identity_supports(self):
        for variant in ("cross_run", "cross_spec", "cross_plan", "unknown", "missing_source"):
            with self.subTest(variant=variant):
                harness, run = self._run()
                rows = copy.deepcopy(run["state"]["verified_results_ledger"])
                calls = copy.deepcopy(run["state"]["calls"])
                for row in rows[:2]:
                    review = calls[row["review_call_id"]]
                    if variant == "cross_run":
                        review["run_id"] = "other-run"
                    elif variant == "cross_spec":
                        row["specification_version"] += 1
                    elif variant == "cross_plan":
                        review["plan_version"] += 1
                    elif variant == "unknown":
                        review["status"] = "unknown_outcome"
                    else:
                        del calls[row["review_call_id"]]
                run = harness.commit_event(run["run_id"],
                    expected_revision=run["state_revision"],
                    event={"event_id": "invalidate-sources", "type": "controlled_source_change"},
                    state_updates={"verified_results_ledger": rows, "calls": calls})
                self.assertEqual("invalidated", self._child(run)[0]["status"])
                self.assertEqual("invalidated", self._child(run)[1]["status"])
