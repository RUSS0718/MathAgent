"""APRS consumes current evidence and replays persisted decision inputs."""
import json
import sqlite3
import unittest
from contextlib import closing
from copy import deepcopy

from showcase.solver_harness.aprs import rate_routes, replay_decision, verified_gain
from tests.star_product_support import StarJobFixture


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
        changed = deepcopy(decision)
        changed["reason"] = "arbitrary_stop"
        self.assertFalse(replay_decision(evaluations, changed))

    def test_only_frozen_prerequisite_goals_gain_credit_and_baseline_cannot_repeat_it(self):
        state = self.state()
        state["problem_spec"] = {"root_obligations": [{"obligation_id": "root:a", "prerequisite_ids": ["g"]}],
                                 "auxiliary_goals": [{"goal_id": "g", "statement": "proof"}, {"goal_id": "unrelated"}]}
        state["plan"] = {"steps": [{"step_id": "s", "auxiliary_goal_ids": ["g", "unrelated"]}]}
        state["steps"] = {"s": {"verification": {"valid": True, "verdict": "ACCEPT"},
                                  "report": {"claims": [{"statement": "proof"}]}}}
        state["verified_results_ledger"] = [{"result_id": "goal-proof", "source": "s", "statement": "proof",
                                             "valid": True, "proven": True, "category": "Lemma", "claim_indexes": [0]}]
        self.assertEqual(["g", "root:a"], verified_gain(state))
        state["route_registry"][0]["credit_at_start"] = ["g", "root:a"]
        evaluations, _ = rate_routes(state)
        self.assertEqual(0, evaluations[0]["vector"]["verified_gain"])

    def test_two_frozen_prerequisites_do_not_share_one_surviving_support(self):
        state = self.state()
        state["problem_spec"] = {"root_obligations": [{"obligation_id": "root:a", "prerequisite_ids": ["g", "h"]}],
            "auxiliary_goals": [{"goal_id": "g", "statement": "g proof"}, {"goal_id": "h", "statement": "h proof"}]}
        state["plan"] = {"steps": [{"step_id": "s", "auxiliary_goal_ids": ["g", "h"]}]}
        state["steps"] = {"s": {"verification": {"valid": True, "verdict": "ACCEPT"},
                                  "report": {"claims": [{"statement": "g proof"}, {"statement": "h proof"}]}}}
        state["verified_results_ledger"] = [
            {"result_id": name, "source": "s", "statement": name + " proof", "claim_indexes": [index],
             "valid": True, "proven": True, "category": "Lemma"} for index, name in enumerate(["g", "h"])]
        state["proof_graph"] = {"current_version": 2, "snapshots": [{"graph_version": 2,
            "attempts": {"g": {"result_id": "g", "status": "invalidated", "conclusion": "g"},
                         "h": {"result_id": "h", "status": "accepted", "conclusion": "h"}},
            "propositions": {"g": {"status": "invalidated"}, "h": {"status": "supported"}}}]}
        self.assertNotIn("g", verified_gain(state))
        self.assertIn("h", verified_gain(state))
        state["obligation_evidence_ledger"][0]["claim_indexes"] = [0, 1]
        self.assertNotIn("root:a", verified_gain(state))


class AprsJobReplayTest(StarJobFixture, unittest.TestCase):
    def test_new_sqlite_reader_replays_actual_job_decision_without_dispatch(self):
        from showcase.run_budget import RunBudgetLimits
        from showcase.solver_harness.storage import SolverStateStore
        from tests.test_faithful_s03_job import FEATURES, REPLIES, SPEC

        replies = deepcopy(REPLIES)
        replies[1]["steps"][0]["method_id"] = "computation"
        self.open_star(replies,
                       SHOWCASE_STAR_FEATURES={**FEATURES, "context_pack": False,
                                               "progress_scheduling": True,
                                               "serial_routes": True},
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8))
        created = self.client.post("/api/agent/jobs", headers=self.headers(), json={
            "message": SPEC["original_problem"], "session_id": self.session,
            "solver_mode": "star_limited", "problem_spec": SPEC})
        self.assertEqual(202, created.status_code)
        job_id = created.get_json()["job_id"]
        self.assertEqual("succeeded", self.terminal(job_id)["status"])
        count = len(self.outbound)
        service = self.app.extensions["showcase_workspace_service"]
        with closing(sqlite3.connect(service.store.database_path)) as connection:
            connection.row_factory = sqlite3.Row
            state = SolverStateStore(connection).get_run(job_id)["state"]
        evaluations = state["route_evaluations"][-1]["evaluations"]
        decision = state["aprs_decisions"][-1]
        self.assertTrue(replay_decision(evaluations, decision))
        evaluations[0]["snapshot"]["frontier_digest"] = "tampered"
        self.assertFalse(replay_decision(evaluations, decision))
        self.assertEqual(count, len(self.outbound))
