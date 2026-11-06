"""Engineering delivery must preserve mathematical rejection and hard stops."""

import unittest

from showcase.solver_harness import ScriptedModelPort, ScriptedVerifierPort, SolverHarness
from showcase.solver_harness.final_binding import delivery_verification, review_binding
from showcase.solver_harness.handoff import delivery_check

PLAN = {"version": 1, "steps": [
    {"step_id": "s1", "title": "derive", "objective": "derive a bound"},
    {"step_id": "s2", "title": "conclude", "objective": "use the bound", "depends_on": ["s1"]},
]}
DISPUTE = {"goal_gate": "PARTIAL", "logic_gate": "UNCERTAIN", "verdict": "CHALLENGE",
           "objection": "The boundary case is missing"}
CONFIG = {"acceptance_mode": "handoff", "max_model_calls": 20,
          "features": {"final_generation": True, "final_solution_review": True,
                       "persistent_sessions": True, "stream_recovery": True}}


class HandoffDeliveryTest(unittest.TestCase):
    def run_case(self, *, config=None, verdict=None):
        model = ScriptedModelPort([
            {"argument": "unproven first draft"}, {"argument": "conditional conclusion"},
            {"final_response": "A complete but disputed answer"},
        ])
        reviewer = ScriptedVerifierPort([DISPUTE, DISPUTE, verdict or {"verdict": "REJECT"}])
        with SolverHarness(model_port=model, verifier_port=reviewer,
                           config=config or CONFIG) as harness:
            run = harness.solve("prove the bound", {"run_id": "handoff", "plan": PLAN})
        return run, model, reviewer

    def test_disputes_are_handed_on_without_becoming_accepted_facts(self):
        run, model, reviewer = self.run_case()
        state = run["state"]
        self.assertEqual("TERMINAL", state["phase"])
        self.assertEqual("completed_unverified", state["status"])
        self.assertEqual("handoff_final_reviewed", state["result_reason"])
        self.assertEqual([], state["accepted_results"])
        self.assertEqual(["REVIEWED", "REVIEWED"], [s["status"] for s in state["steps"].values()])
        prior = model.requests[1]["role_context"]["state"]["reviewed_drafts"]
        self.assertEqual("unproven first draft", prior[0]["report"]["argument"])
        self.assertEqual("CHALLENGE", prior[0]["review"]["verdict"])
        self.assertEqual([], model.requests[-1]["accepted_results"])
        self.assertEqual(2, len(model.requests[-1]["reviewed_drafts"]))
        self.assertEqual(model.requests[-1]["reviewed_drafts"], reviewer.requests[-1]["reviewed_drafts"])
        self.assertEqual({"whole_review": "rejected", "binding": "same_artifact"},
                         review_binding(run, state["final_response"]))
        self.assertFalse(delivery_verification(run, state["final_response"])[0])
        self.assertEqual("PASS", delivery_check(run, state["final_response"])["status"])
        self.assertEqual("FAIL", delivery_check(run, "rewritten after review")["status"])

    def test_default_contract_still_stops_for_mathematical_dispute(self):
        run, model, _ = self.run_case(config={k: v for k, v in CONFIG.items() if k != "acceptance_mode"})
        self.assertNotEqual("handoff_final_reviewed", run["state"].get("result_reason"))
        self.assertNotIn("final_generator", [r["role"] for r in model.requests])

    def test_invalid_review_is_not_an_engineering_delivery(self):
        run, _, _ = self.run_case(verdict={"verdict": "MAYBE"})
        self.assertNotEqual("handoff_final_reviewed", run["state"].get("result_reason"))
        self.assertNotEqual("same_artifact", review_binding(run, run["state"].get("final_response", ""))["binding"])

    def test_budget_remains_a_hard_stop(self):
        run, model, _ = self.run_case(config={**CONFIG, "max_model_calls": 2})
        self.assertEqual("partial_budget_exhausted", run["state"]["status"])
        self.assertEqual(1, len(model.requests))

    def test_unfulfilled_tool_request_is_not_a_mathematical_dispute(self):
        model = ScriptedModelPort([{"argument": "unproven draft"}])
        reviewer = ScriptedVerifierPort([{**DISPUTE, "tool_request": {
            "tool": "python_math", "arguments": {"code": "print(1)"},
            "scope": "finite_computation", "expected_output": "1"}}])
        with SolverHarness(model_port=model, verifier_port=reviewer, config=CONFIG) as harness:
            run = harness.solve("prove", {"plan": PLAN})
        self.assertEqual("FAIL", delivery_check(run, run["state"].get("final_response", ""))["status"])
        self.assertNotIn("final_generator", [r["role"] for r in model.requests])

    def test_control_requests_are_routed_instead_of_marked_reviewed(self):
        for verdict in ("TRACE_BACK", "PROPOSE_REPLAN"):
            with self.subTest(verdict=verdict):
                model = ScriptedModelPort([{"argument": "draft"}])
                reviewer = ScriptedVerifierPort([{**DISPUTE, "verdict": verdict, "trace_back_to": 1}])
                with SolverHarness(model_port=model, verifier_port=reviewer, config=CONFIG) as harness:
                    run = harness.solve("prove", {"plan": PLAN})
                self.assertNotEqual("REVIEWED", run["state"]["steps"]["s1"]["status"])
                self.assertNotIn("final_generator", [r["role"] for r in model.requests])

    def test_unknown_modes_and_best_effort_combination_are_rejected(self):
        for config in ({**CONFIG, "acceptance_mode": "typo"},
                       {**CONFIG, "features": {**CONFIG["features"], "best_effort": True}}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                SolverHarness(config=config)
