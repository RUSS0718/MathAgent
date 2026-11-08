"""APRS consumes current evidence and replays persisted decision inputs."""
import json
import unittest
from copy import deepcopy

from showcase.solver_harness.aprs import rate_routes, replay_decision, verified_gain


class AprsReplayTest(unittest.TestCase):
    def state(self):
        return {"run_id": "r", "state_revision": 4, "specification_version": 1,
                "route_policy": {"policy_version": "serial-aprs-v1"},
                "obligation_ledger": [{"obligation_id": "root:a", "status": "satisfied", "evidence_refs": ["e"]}],
                "obligation_evidence_ledger": [{"evidence_id": "e", "obligation_id": "root:a", "source": "s",
                                                "claim_indexes": [0], "valid": True, "specification_version": 1}],
                "route_registry": [{"route_id": "r1", "status": "active", "frontier_digest": "f",
                                    "frontier": [{"objective_id": "root:a"}],
                                    "budget_at_start": {"charged_tokens": 10, "http_attempts": 1}}],
                "route_budget": {"current_snapshot": {"charged_tokens": 30, "http_attempts": 3,
                                                       "tool_calls": 0, "unknown_attempts": 0}}}

    def test_persisted_inputs_recompute_vectors_and_reject_tampering(self):
        evaluations, decision = rate_routes(self.state())
        persisted = json.loads(json.dumps([evaluations, decision]))
        self.assertTrue(replay_decision(*persisted))
        self.assertEqual(20, evaluations[0]["vector"]["cost"])
        self.assertEqual(2, evaluations[0]["vector"]["http_attempts"])
        evaluations[0]["vector"]["verified_gain"] += 1
        self.assertFalse(replay_decision(evaluations, decision))

    def test_graph_invalidated_source_cannot_keep_root_credit(self):
        state = self.state()
        state["verified_results_ledger"] = [{"result_id": "result", "source": "s", "claim_indexes": [0]}]
        state["proof_graph"] = {"current_version": 2, "snapshots": [{"graph_version": 2,
            "attempts": {"a": {"result_id": "result", "status": "invalidated", "conclusion": "p"}},
            "propositions": {"p": {"status": "invalidated", "conflict": False}}}]}
        self.assertEqual([], verified_gain(state))

    def test_unknown_consumption_is_not_imputed_as_zero(self):
        state = self.state()
        state["route_budget"]["current_snapshot"]["unknown_attempts"] = 1
        evaluations, decision = rate_routes(state)
        self.assertIsNone(evaluations[0]["vector"]["cost"])
        self.assertTrue(replay_decision(evaluations, decision))
        changed = deepcopy(decision)
        changed["selected_route_id"] = "another"
        self.assertFalse(replay_decision(evaluations, changed))

    def test_only_frozen_prerequisite_goals_gain_credit_and_baseline_cannot_repeat_it(self):
        state = self.state()
        state["problem_spec"] = {"root_obligations": [{"obligation_id": "root:a", "prerequisite_ids": ["g"]}],
                                 "auxiliary_goals": [{"goal_id": "g"}, {"goal_id": "unrelated"}]}
        state["plan"] = {"steps": [{"step_id": "s", "auxiliary_goal_ids": ["g", "unrelated"]}]}
        state["steps"] = {"s": {"verification": {"valid": True, "verdict": "ACCEPT"},
                                  "report": {"claims": [{"statement": "proof"}]}}}
        self.assertEqual(["g", "root:a"], verified_gain(state))
        state["route_registry"][0]["credit_at_start"] = ["g", "root:a"]
        evaluations, _ = rate_routes(state)
        self.assertEqual(0, evaluations[0]["vector"]["verified_gain"])
