"""Injected history keeps distinct verdicts while referencing identical current prefixes."""

import unittest
from copy import deepcopy

from showcase.solver_harness import SolverHarness
from showcase.solver_harness.sessions import prepare_session


class SessionHistoryDedupTest(unittest.TestCase):
    def test_only_exact_prefix_is_referenced_and_old_dialogue_is_reconstructable(self):
        with SolverHarness() as harness:
            run = harness.solve("question", {"run_id": "history-dedup"})
        request = {"role": "step_verifier", "call_id": "new", "step": {"step_id": "s1"},
                   "challenge_history": [{"round": 1, "verdict": "CHALLENGE"},
                                         {"round": 2, "verdict": "CHALLENGE"}]}
        record, _ = prepare_session(run, request)
        old = deepcopy(request)
        old["call_id"] = "old"
        old["challenge_history"][-1]["verdict"] = None
        record["history"] = [{"request": old, "response": {"verdict": "CHALLENGE"}}]
        run["state"]["session_registry"] = {record["session_key"]: record}
        original = deepcopy(run)
        _, prepared = prepare_session(run, request)
        projected = prepared["session_history"][0]["request"]
        ref = projected["challenge_history_prefix_ref"]
        self.assertEqual(1, ref["length"])
        self.assertEqual("current_request.challenge_history", ref["source"])
        self.assertEqual(old["challenge_history"], request["challenge_history"][:ref["length"]] + projected["challenge_history"])
        self.assertEqual(original, run)
        self.assertEqual(request["challenge_history"], prepared["challenge_history"])
        self.assertEqual(record["history"][0]["response"], prepared["session_history"][0]["response"])

    def test_other_step_or_different_prefix_is_retained(self):
        with SolverHarness() as harness:
            run = harness.solve("question", {"run_id": "history-guard"})
        request = {"role": "reasoner", "call_id": "new", "step": {"step_id": "s2"},
                   "challenge_history": [{"round": 1, "verdict": "CHALLENGE"}]}
        record, _ = prepare_session(run, request)
        for step, history in (("s1", request["challenge_history"]), ("s2", [{"different": True}])):
            with self.subTest(step=step, history=history):
                old = {**request, "step": {"step_id": step}, "challenge_history": history}
                record["history"] = [{"request": old, "response": {"argument": "proof"}}]
                run["state"]["session_registry"] = {record["session_key"]: record}
                _, prepared = prepare_session(run, request)
                self.assertEqual(record["history"], prepared["session_history"])
