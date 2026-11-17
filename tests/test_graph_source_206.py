"""Public Harness regression for equivalent checkpoint supports (controlled)."""

import copy
import unittest

from showcase.solver_harness import ScriptedModelPort, ScriptedVerifierPort, SolverHarness
from tests.test_solver_harness_reasoner_checkpoint import checkpoint


class GraphSource206Test(unittest.TestCase):
    def _solve(self, variant="equivalent", *, retry=False):
        """Execute controlled checkpoints through persisted public Harness seams."""
        parent_yield = checkpoint(marker="parent-1")
        parent_final = checkpoint("FINAL", marker="parent-2")
        for reply in (parent_yield, parent_final):
            reply["checkpoint"]["claims"][0]["statement"] = "parent result"
        child = checkpoint("FINAL", marker="child")
        child["checkpoint"]["dependencies"] = ["s1"]
        accept = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
                  "objection": ""}
        parent_review = {**accept, "classified_outcomes": [{"category": "Lemma",
            "statement": "parent result", "scope": "derive", "claim_indexes": [0]}]}
        second_review = copy.deepcopy(parent_review)
        if variant == "distinct":
            parent_final["checkpoint"]["claims"][0]["statement"] = "another result"
            second_review["classified_outcomes"][0]["statement"] = "another result"
        child_review = {**accept, "classified_outcomes": [{"category": "Lemma",
            "statement": "child", "scope": "derive", "claim_indexes": [0],
            "dependencies": ["s1"]}]}
        verifier = ScriptedVerifierPort([parent_review, second_review, child_review, child_review])

        def consume(request):
            if variant not in {"equivalent", "distinct"}:
                run = harness.get_run("equivalent-supports")
                rows = copy.deepcopy(run["state"]["verified_results_ledger"])
                calls = copy.deepcopy(run["state"]["calls"])
                for row in rows:
                    review = calls[row["review_call_id"]]
                    if variant == "invalidated":
                        row.update(valid=False, invalidated=True)
                    elif variant == "cross_spec":
                        row["specification_version"] += 1
                    elif variant == "cross_run":
                        review["run_id"] = "other-run"
                    elif variant == "cross_plan":
                        review["plan_version"] += 1
                    elif variant == "unknown":
                        review["status"] = "unknown_outcome"
                    elif variant == "missing_source":
                        calls.pop(row["review_call_id"])
                harness.commit_event(run["run_id"], expected_revision=run["state_revision"],
                    event={"event_id": "source-change", "type": "controlled_source_change"},
                    state_updates={"calls": calls, "verified_results_ledger": rows})
            return child

        class SourceChangePort(ScriptedModelPort):
            def complete(self, request):
                if len(self._responses) == 1:
                    consume(request)
                return super().complete(request)

        model = SourceChangePort([parent_yield, parent_final,
            *([checkpoint(marker="blocked", blocked=True)] if retry else []), child])
        meta = ScriptedModelPort([{"action_type": "retry_different_method",
            "specific_task": "derive child", "use_pure_reasoning": True,
            "trace_back_to": None, "rationale": "controlled retry"}])
        with SolverHarness(config={"features": {"proof_graph": True,
                "reasoner_checkpoints": True, "stream_recovery": True,
                "meta_guidance": True}, "max_model_calls": 10},
                model_port=model, meta_port=meta, verifier_port=verifier) as harness:
            result = harness.solve("controlled", {"run_id": "equivalent-supports", "plan": {
                "version": 1, "steps": [
                    {"step_id": "s1", "title": "Parent", "objective": "derive"},
                    {"step_id": "s2", "title": "Child", "objective": "derive",
                     "depends_on": ["s1"]}]}})
        return result["state"], verifier, model

    def test_equivalent_parent_checkpoints_back_child_without_reclassification(self):
        state, verifier, _model = self._solve()
        self.assertEqual("FINAL_GENERATE", state["phase"], state.get("result_reason"))
        self.assertEqual(3, len(verifier.requests))
        self.assertFalse(state.get("dependency_reclassifications"))
        rows = state["verified_results_ledger"]
        self.assertEqual(3, len(rows))
        self.assertIn(rows[2]["dependencies"][0], {row["result_id"] for row in rows[:2]})

    def test_new_attempt_can_consume_unaffected_parent_supports(self):
        state, verifier, model = self._solve(retry=True)
        self.assertEqual("FINAL_GENERATE", state["phase"], state.get("result_reason"))
        self.assertEqual(1, state["attempt_index"])
        self.assertEqual(3, len(verifier.requests))
        self.assertFalse(state.get("dependency_reclassifications"))
        rows = state["verified_results_ledger"]
        self.assertEqual([0, 0, 1], [row["attempt_index"] for row in rows])
        self.assertIn(rows[2]["dependencies"][0], {row["result_id"] for row in rows[:2]})
        sources = model.requests[-1]["valid_sources"]
        self.assertTrue({row["result_id"] for row in rows[:2]}.issubset(
            {row.get("result_id") for row in sources}))

    def test_distinct_parent_propositions_remain_ambiguous(self):
        state, _verifier, _model = self._solve("distinct")
        self.assertNotEqual("FINAL_GENERATE", state["phase"])
        self.assertEqual("unsupported_graph_step_dependency", state["result_reason"])
        self.assertEqual(2, len(state["verified_results_ledger"]))

    def test_invalid_or_unbound_sources_cannot_promote_child(self):
        for variant in ("invalidated", "cross_spec", "cross_run", "cross_plan",
                        "unknown", "missing_source"):
            with self.subTest(variant=variant):
                state, _verifier, _model = self._solve(variant)
                self.assertNotEqual("FINAL_GENERATE", state["phase"])
                self.assertFalse(any(row["source"] == "s2"
                    for row in state["verified_results_ledger"]))
                snapshot = state["proof_graph"]["snapshots"][-1]
                self.assertFalse(any(row["status"] == "accepted"
                    for row in snapshot["derivations"].values()))
