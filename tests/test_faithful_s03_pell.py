"""C04 Pell enumeration, completeness, filtering, and format acceptance."""

import unittest

from showcase.solver_harness import ScriptedModelPort, ScriptedVerifierPort, SolverHarness

SPEC_CONFIG = {
    "features": {
        "problem_spec": True,
        "final_generation": True,
        "final_solution_review": True,
    }
}


class FaithfulS03PellAcceptanceTest(unittest.TestCase):
    def test_candidate_list_does_not_close_completeness_obligation(self):
        problem = "List all Pell solutions below B."
        spec = {
            "specification_version": 1,
            "original_problem": problem,
            "domain": "positive integer pairs",
            "quantifiers": ["all solutions below B"],
            "assumptions": ["B is fixed"],
            "directions": ["enumerate all solutions"],
            "output_requirements": ["list solutions", "prove completeness"],
            "root_obligations": [
                {"obligation_id": "root:list", "obligation_type": "enumeration",
                 "statement": "List the solutions below B."},
                {"obligation_id": "root:complete", "obligation_type": "completeness",
                 "statement": "No solution below B is omitted."},
            ],
        }
        plan = {"version": 1, "steps": [{
            "step_id": "enumerate", "title": "enumerate", "objective": "list all solutions",
            "obligation_ids": ["root:list", "root:complete"],
        }]}
        model = ScriptedModelPort([{
            "argument": "Candidate solutions: (1,1), (2,3), (5,12).",
            "claims": [{"statement": "The candidate list is (1,1), (2,3), (5,12)."}],
        }])
        verifier = ScriptedVerifierPort([{
            "goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
            "obligation_evidence": [{
                "obligation_id": "root:list", "evidence_category": "enumeration_result",
                "claim_indexes": [0],
            }],
        }])

        with SolverHarness(
            config={**SPEC_CONFIG, "max_model_calls": 4},
            model_port=model,
            verifier_port=verifier,
        ) as harness:
            result = harness.solve(problem, {
                "run_id": "pell-list-not-complete", "problem_spec": spec, "plan": plan,
            })

        self.assertEqual(["satisfied", "open"], [
            item["status"] for item in result["state"]["obligation_ledger"]
        ])
        self.assertEqual("root_obligations_incomplete", result["state"]["result_reason"])
        self.assertEqual(["reasoner"], [item["role"] for item in model.requests])

    def test_closeout_waits_for_all_four_typed_pell_obligations(self):
        from showcase.run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget

        problem = "List every Pell solution below B, filter by parity, and use ordered pairs."
        spec = {
            "specification_version": 1,
            "original_problem": problem,
            "domain": "positive integer pairs",
            "quantifiers": ["all solutions below B"],
            "assumptions": ["B is fixed"],
            "directions": ["complete enumeration"],
            "output_requirements": ["apply parity filter", "use ordered pairs"],
            "root_obligations": [
                {"obligation_id": "root:list", "obligation_type": "enumeration",
                 "statement": "List the solutions below B."},
                {"obligation_id": "root:complete", "obligation_type": "completeness",
                 "statement": "No solution below B is omitted."},
                {"obligation_id": "root:filter", "obligation_type": "filtering",
                 "statement": "Apply the requested parity filter.",
                 "prerequisite_ids": ["root:list", "root:complete"]},
                {"obligation_id": "root:format", "obligation_type": "format",
                 "statement": "Render the surviving values as ordered pairs.",
                 "prerequisite_ids": ["root:filter"]},
            ],
        }
        plan = {"version": 1, "steps": [
            {"step_id": "enumerate", "title": "enumerate", "objective": "list all solutions",
             "obligation_ids": ["root:list", "root:complete"]},
            {"step_id": "filter", "title": "filter", "objective": "apply parity",
             "obligation_ids": ["root:filter"]},
            {"step_id": "format", "title": "format", "objective": "render ordered pairs",
             "obligation_ids": ["root:format"]},
        ]}
        model = ScriptedModelPort([
            {"argument": "Enumerated and proved complete below B.", "claims": [
                {"statement": "The listed pairs satisfy the Pell equation and bound."},
                {"statement": "The recurrence and bound argument exclude every omitted pair."},
            ]},
            {"argument": "Applied the parity requirement to every listed pair.", "claims": [
                {"statement": "Each retained pair satisfies the requested parity condition."},
            ]},
            {"argument": "Rendered each retained value as an ordered pair.", "claims": [
                {"statement": "The result is formatted as ordered pairs."},
            ]},
            {"final_response": "(1,1), (5,12)"},
        ])
        verifier = ScriptedVerifierPort([
            {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
             "obligation_evidence": [
                 {"obligation_id": "root:list", "evidence_category": "enumeration_result",
                  "claim_indexes": [0]},
                 {"obligation_id": "root:complete", "evidence_category": "completeness_proof",
                  "claim_indexes": [1]},
             ]},
            {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
             "obligation_evidence": [{
                 "obligation_id": "root:filter", "evidence_category": "filtering_proof",
                 "claim_indexes": [0],
             }]},
            {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
             "obligation_evidence": [{
                 "obligation_id": "root:format", "evidence_category": "format_check",
                 "claim_indexes": [0],
             }]},
            {"verdict": "ACCEPT"},
        ])

        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure(
            "pell-four-obligations",
            RunBudgetLimits(max_model_calls=16, max_http_attempts=16, max_tokens=100_000),
        )
        with bind_budget(budget), SolverHarness(
            config={**SPEC_CONFIG, "max_model_calls": 16},
            model_port=model,
            verifier_port=verifier,
        ) as harness:
            result = harness.solve(problem, {
                "run_id": "pell-four-obligations", "problem_spec": spec, "plan": plan,
            })

        self.assertEqual("completed_llm_reviewed", result["state"]["status"], result["state"])
        self.assertTrue(all(item["status"] == "satisfied"
                            for item in result["state"]["obligation_ledger"]))
        self.assertEqual("(1,1), (5,12)", result["state"]["final_response"])
        self.assertEqual(
            ["reasoner", "reasoner", "reasoner", "final_generator"],
            [item["role"] for item in model.requests],
        )
        self.assertEqual("whole_solution_verifier", verifier.requests[-1]["role"])


if __name__ == "__main__":
    unittest.main()
