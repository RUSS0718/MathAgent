"""Action ranking records unknown features rather than inventing model scores."""

import unittest


class ActionRankingTest(unittest.TestCase):
    def test_ranking_is_deterministic_and_does_not_promote_observations_to_gain(self):
        from showcase.solver_harness.faithful_intervention_actions import rank_actions

        state = {"current_step": "s", "plan": {"steps": [
            {"step_id": "s", "method_id": "direct", "obligation_ids": ["root:a"]}]},
            "obligation_ledger": [{"obligation_id": "root:a", "status": "open"}]}
        actions = [{"action_id": "a", "target": "s", "parameters": {"method_id": "direct"}},
                   {"action_id": "b", "target": "s", "parameters": {"method_id": "induction"}}]
        ranked = rank_actions(state, actions)
        self.assertEqual(ranked, rank_actions(state, list(reversed(actions))))
        self.assertEqual("b", ranked[0]["action_id"])
        self.assertIsNone(ranked[0]["expected_verified_progress"])
        self.assertIsNone(ranked[0]["actual_token_cost"])
        self.assertNotIn("verified_gain", state)

    def test_missing_method_does_not_gain_distinguishability(self):
        from showcase.solver_harness.faithful_intervention_actions import rank_actions

        state = {"plan": {"steps": [{"step_id": "s", "method_id": "direct"}]}}
        ranked = rank_actions(state, [
            {"action_id": "a", "target": "s", "parameters": {}},
            {"action_id": "b", "target": "s", "parameters": {"method_id": "direct"}}])
        self.assertEqual("b", ranked[0]["action_id"])
        self.assertIsNone(ranked[1]["hypothesis_distinguishability"])


if __name__ == "__main__":
    unittest.main()
