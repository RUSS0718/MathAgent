"""Same-checkpoint native Solver actions use isolated state and current review."""

import json
import unittest
from copy import deepcopy

from tests import test_faithful_s10_intervention_execution as support


class NativeCheckpointTest(unittest.TestCase):
    setUp = support.InterventionExecutionTest.setUp
    reserve = support.InterventionExecutionTest.reserve

    def test_control_action_must_match_the_checkpoint_method(self):
        from showcase.solver_harness.faithful_intervention_native import NativeCheckpointExecutor
        from showcase.solver_harness.faithful_intervention_records import (
            FaithfulInterventionError,
            ProofAction,
        )

        executor = NativeCheckpointExecutor(self.engine, config={"features": {"stream_recovery": True}},
                                            problem="2+2", model_port=None, verifier_port=None)
        state = {
            "phase": "STEP_EXECUTE", "problem_spec": {}, "route_policy": {"enabled": True},
            "population_policy": {"enabled": False}, "plan": {"steps": [
                {"step_id": "step-1", "method_id": "direct"}]}, "current_step": "step-1",
            "steps": {}, "calls": {},
        }
        wrong_control = ProofAction("wrong", "reasoning_method", "step-1",
                                    {"method_id": "induction"})
        with self.assertRaisesRegex(FaithfulInterventionError, "native_control_action_mismatch"):
            executor.validate_checkpoint(state, wrong_control, is_control=True)

    def test_native_executor_rejects_non_action_checkpoint_before_dispatch(self):
        from showcase.solver_harness.faithful_intervention_native import NativeCheckpointExecutor
        from showcase.solver_harness.faithful_intervention_records import FaithfulInterventionError

        executor = NativeCheckpointExecutor(self.engine, config={"profile": "test"},
                                            problem="2+2", model_port=None,
                                            verifier_port=None)
        with self.assertRaises(FaithfulInterventionError):
            executor.validate_checkpoint(self.parent["state"], self.engine.get_action("control"))

    def test_native_children_are_independently_reviewed_and_parent_is_unchanged(self):
        from showcase.run_budget import RunBudgetLimits, current_budget
        from showcase.solver_harness import SolverHarness
        from showcase.solver_harness.faithful_intervention_native import (
            NativeCheckpointExecutor,
            execute_native_pair,
        )
        from showcase.solver_harness.routes import sync_plan_route
        from showcase.solver_harness.storage import SolverStateStore
        from tests.test_faithful_s03_job import REPLIES, SPEC

        config = {"max_model_calls": 20, "features": {
            "problem_spec": True, "progress_scheduling": True, "serial_routes": True, "proof_graph": True,
            "stream_recovery": True, "persistent_sessions": True,
            "final_generation": True, "final_solution_review": True}}
        plan = deepcopy(REPLIES[1])
        plan["steps"][0]["method_id"] = "direct"
        with SolverHarness(store=self.store, config=config) as harness:
            run = harness.solve(SPEC["original_problem"], {
                "run_id": "native-parent", "problem_spec": SPEC, "plan": plan})
            run = harness.commit_event("native-parent", expected_revision=run["state_revision"],
                event={"event_id": "ready", "type": "initial_plan_generated"},
                state_updates={"phase": "STEP_EXECUTE", "plan": plan, "plan_version": 1,
                               "current_step": plan["steps"][0]["step_id"]})
            run = sync_plan_route(harness, run)
        self.ledger.ensure("native-parent", RunBudgetLimits(
            max_model_calls=10, max_http_attempts=10, max_tool_calls=0,
            max_tokens=20000, max_runtime_seconds=120))
        for action_id, method in (("native-control", "direct"), ("native-variant", "induction")):
            self.engine.register_action({"action_id": action_id, "action_type": "reasoning_method",
                "target": plan["steps"][0]["step_id"], "parameters": {"method_id": method}})
        self.engine.register_hypothesis({"hypothesis_id": "native-hyp", "failure_category": "method_mismatch",
            "evidence": {"event_id": "ready"},
            "candidate_action_ids": ["native-control", "native-variant"],
            "falsification_criteria": {"condition": "no accepted root gain"}})
        self.engine.reserve_pair(job_id="native-parent", job_gate=self.gate, run_id="native-parent",
            expected_revision=run["state_revision"], hypothesis_id="native-hyp",
            control_action_id="native-control", intervention_action_id="native-variant",
            pair_id="native-pair", seed=7, reservation={"input_estimate": 1000,
                "output_cap": 1000, "model_calls": 3, "tool_calls": 0, "time_seconds": 30})
        requests = []

        class Port:
            def reply(self, request, reply):
                requests.append(deepcopy(request))
                call = current_budget().model_call(request["role"], solver_call_id=request["call_id"])
                event = {"attempt_id": current_budget().ledger.branch_id + request["call_id"] + ":http", "max_tokens": 100}
                call.before_attempt(event, input_estimate=100)
                call.after_attempt({**event, "status": "success", "prompt_tokens": 4,
                                    "completion_tokens": 3, "total_tokens": 7})
                return deepcopy(reply)

            def complete(self, request):
                return self.reply(request, REPLIES[2])

            def verify(self, request):
                return self.reply(request, REPLIES[3])

        port = Port()
        executor = NativeCheckpointExecutor(self.engine, config=config,
            problem=SPEC["original_problem"], model_port=port, verifier_port=port)
        report = execute_native_pair(self.engine, "native-pair", executor=executor,
                                     ledger=self.ledger, job_gate=self.gate)
        self.assertEqual("native_solver_checkpoint", report["branch_engine"])
        self.assertEqual(1, report["evaluable_pairs"], report)
        self.assertEqual(6, self.ledger.snapshot("native-parent")["http_attempts"])
        self.assertEqual(run, SolverStateStore(self.connection).get_run("native-parent"))
        children = self.connection.execute(
            "SELECT state_json FROM faithful_intervention_children WHERE pair_id='native-pair'").fetchall()
        self.assertEqual(2, len(children))
        self.assertTrue(all(json.loads(row[0])["state_revision"] > run["state_revision"] for row in children))
        for row in children:
            child = json.loads(row[0])
            for evidence in child["obligation_evidence_ledger"]:
                self.assertIn(evidence["review_call_id"], child["calls"])
        methods = [item["step"]["method_id"] for item in requests if item["role"] == "reasoner"]
        self.assertEqual({"direct", "induction"}, set(methods))
        from showcase.solver_harness.faithful_intervention_effects import aggregate_pairs
        verifier_requests = [item for item in requests if item["role"] == "step_verifier"]
        self.assertEqual(4, len(verifier_requests))
        self.assertEqual(4, len({item["call_id"] for item in verifier_requests}))

        self.assertEqual(1, aggregate_pairs(self.engine)["evaluable_pairs"])
        reviews = self.connection.execute(
            "SELECT arm,status FROM faithful_intervention_reviews WHERE pair_id='native-pair' "
            "ORDER BY arm"
        ).fetchall()
        self.assertEqual([("control", "reviewed"), ("intervention", "reviewed")],
                         [tuple(item) for item in reviews])
        budget_row = self.connection.execute(
            "SELECT ledger_json FROM run_budgets WHERE run_id='native-parent'"
        ).fetchone()
        original_ledger = budget_row[0]
        ledger = json.loads(original_ledger)
        original_review_json = self.connection.execute(
            "SELECT state_json FROM faithful_intervention_reviews "
            "WHERE pair_id='native-pair' AND arm='control'"
        ).fetchone()[0]
        review_state = json.loads(original_review_json)
        child_state = json.loads(self.connection.execute(
            "SELECT state_json FROM faithful_intervention_children "
            "WHERE pair_id='native-pair' AND arm='control'"
        ).fetchone()[0])
        review_call = next(
            call_id for call_id, call in review_state["calls"].items()
            if call["role"] == "step_verifier" and call["status"] == "completed"
            and call_id not in child_state["calls"]
        )
        action = next(item for item in ledger["actions"]
                      if item.get("reservation_id") == "native-pair"
                      and item.get("role") == "faithful_intervention:native-pair:control"
                      and item.get("kind") == "http"
                      and item.get("solver_call_id") == review_call)
        action["solver_call_id"] = "unbound-review-call"
        self.connection.execute(
            "UPDATE run_budgets SET ledger_json=? WHERE run_id='native-parent'",
            (json.dumps(ledger),),
        )
        self.connection.commit()
        unbound = self.engine.get_pair("native-pair")
        self.assertEqual("rejected", unbound["arms"]["control"]["evidence_integrity"])
        self.connection.execute(
            "UPDATE run_budgets SET ledger_json=? WHERE run_id='native-parent'",
            (original_ledger,),
        )
        self.connection.commit()
        self.assertEqual("verified", self.engine.get_pair("native-pair")["arms"]["control"][
            "evidence_integrity"])
        review_state["calls"][review_call]["request"]["report"]["argument"] = "tampered report"
        self.connection.execute(
            "UPDATE faithful_intervention_reviews SET state_json=? "
            "WHERE pair_id='native-pair' AND arm='control'",
            (json.dumps(review_state),),
        )
        self.connection.commit()
        unbound_report = self.engine.get_pair("native-pair")
        self.assertEqual("rejected", unbound_report["arms"]["control"]["evidence_integrity"])
        self.connection.execute(
            "UPDATE faithful_intervention_reviews SET state_json=? "
            "WHERE pair_id='native-pair' AND arm='control'",
            (original_review_json,),
        )
        self.connection.commit()
        verifier_calls = [item for item in requests if item["role"] == "step_verifier"]
        self.assertEqual(4, len(verifier_calls))
        self.assertEqual(4, len({item["call_id"] for item in verifier_calls}))
        raw = self.connection.execute(
            "SELECT report_json FROM faithful_intervention_pairs WHERE pair_id='native-pair'").fetchone()[0]
        changed = json.loads(raw)
        changed["arms"]["control"]["measurement"] = 999
        self.connection.execute(
            "UPDATE faithful_intervention_pairs SET report_json=? WHERE pair_id='native-pair'",
            (json.dumps(changed),))
        self.connection.commit()
        rejected = self.engine.get_pair("native-pair")
        self.assertIsNone(rejected["effect"])
        self.assertEqual("rejected", rejected["arms"]["control"]["evidence_integrity"])
        self.assertEqual(1, aggregate_pairs(self.engine)["denominator"])


if __name__ == "__main__":
    unittest.main()
