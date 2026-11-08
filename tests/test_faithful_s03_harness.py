import unittest

from showcase.solver_harness import (
    SolverHarness,
    SolverIdentityError,
    SolverRevisionConflictError,
    SolverRunNotFoundError,
    SolverValidationError,
)


def problem_spec(problem, *, version=1):
    return {
        "specification_version": version,
        "original_problem": problem,
        "domain": "integers",
        "quantifiers": ["for all integers n"],
        "assumptions": ["n is an integer"],
        "directions": ["necessary", "sufficient"],
        "output_requirements": ["prove both directions"],
        "root_obligations": [
            {"obligation_id": "root:necessary", "obligation_type": "universal",
             "direction": "necessary", "statement": "Every solution satisfies the condition."},
            {"obligation_id": "root:sufficient", "obligation_type": "universal",
             "direction": "sufficient", "statement": "Every listed value is a solution."},
        ],
        "auxiliary_goals": [{"goal_id": "aux:factor", "description": "Factor the expression."}],
    }


SPEC_CONFIG = {
    "features": {
        "problem_spec": True,
        "final_generation": True,
        "final_solution_review": True,
    }
}


class ProblemSpecHarnessTest(unittest.TestCase):
    def test_opt_in_run_freezes_full_spec_and_independent_version(self):
        problem = "  Find all integer solutions.\nShow both directions.  "
        supplied = problem_spec(problem, version=7)
        with SolverHarness(config=SPEC_CONFIG) as harness:
            run = harness.solve(problem, {"run_id": "s03-spec", "problem_spec": supplied})
            restored = harness.get_run("s03-spec", problem=problem)

        state = run["state"]
        self.assertEqual(restored, run)
        self.assertEqual(problem, state["problem_spec"]["original_problem"])
        self.assertEqual(7, state["specification_version"])
        self.assertEqual({"enabled": True, "version": "problem-spec-v1"},
                         state["problem_spec_policy"])
        self.assertEqual(2, len(state["obligation_ledger"]))
        self.assertEqual("open", state["obligation_ledger"][0]["status"])
        self.assertEqual([], state["work_units"])

    def test_specification_requires_explicit_feature_and_matching_original_problem(self):
        problem = "Prove both directions."
        with SolverHarness() as harness:
            with self.assertRaises(SolverValidationError):
                harness.solve(problem, {"problem_spec": problem_spec(problem)})

        with SolverHarness(config=SPEC_CONFIG) as harness:
            with self.assertRaises(SolverValidationError):
                harness.solve(problem, {"run_id": "missing-spec"})
            with self.assertRaises(SolverRunNotFoundError):
                harness.get_run("missing-spec")
            with self.assertRaises(SolverValidationError):
                harness.solve(problem, {"problem_spec": problem_spec("different problem")})

    def test_spec_is_frozen_on_resume_and_old_runs_remain_unmigrated(self):
        problem = "Prove both directions."
        original = problem_spec(problem)
        store_harness = SolverHarness(config=SPEC_CONFIG)
        store_harness.solve(problem, {"run_id": "frozen", "problem_spec": original})
        revised = problem_spec(problem, version=2)
        revised["assumptions"] = ["a changed assumption"]
        with self.assertRaises(SolverIdentityError):
            store_harness.solve(problem, {"run_id": "frozen", "problem_spec": revised})
        store_harness.close()

        with SolverHarness() as legacy:
            old = legacy.solve(problem, {"run_id": "legacy"})
            self.assertNotIn("problem_spec", old["state"])
            self.assertNotIn("specification_version", old["state"])
            self.assertEqual(old, legacy.get_run("legacy"))

    def test_supplied_plan_is_recorded_as_work_units_with_root_mapping(self):
        problem = "Prove both directions."
        spec = problem_spec(problem)
        plan = {
            "version": 1,
            "steps": [
                {"step_id": "both", "title": "both directions", "objective": "prove",
                 "obligation_ids": ["root:necessary", "root:sufficient"]},
            ],
        }
        with SolverHarness(config=SPEC_CONFIG) as harness:
            run = harness.solve(problem, {"run_id": "mapped", "problem_spec": spec, "plan": plan})

        self.assertEqual(["root:necessary", "root:sufficient"],
                         run["state"]["work_units"][0]["obligation_ids"])
        self.assertEqual(run["state"]["work_units"], [
            {"work_unit_id": "both", "obligation_ids": ["root:necessary", "root:sufficient"],
             "auxiliary_goal_ids": [], "prerequisites": [], "step_id": "both"}
        ])

    def test_specification_protocol_fields_are_added_only_to_opted_in_requests(self):
        from showcase.solver_harness.intern_schemas import response_schema

        default_verifier = response_schema({"role": "step_verifier"})
        spec_verifier = response_schema({"role": "step_verifier", "problem_spec": {}})
        default_planner = response_schema({"role": "planner"})
        spec_planner = response_schema({"role": "planner", "problem_spec": {}})

        self.assertNotIn("obligation_evidence", default_verifier["properties"])
        self.assertIn("obligation_evidence", spec_verifier["properties"])
        self.assertNotIn(
            "obligation_ids", default_planner["properties"]["steps"]["items"]["properties"]
        )
        self.assertIn(
            "obligation_ids", spec_planner["properties"]["steps"]["items"]["properties"]
        )

    def test_context_pack_carries_the_frozen_specification_version(self):
        problem = "Prove both directions."
        config = {
            **SPEC_CONFIG,
            "features": {**SPEC_CONFIG["features"], "context_pack": True},
            "context_capacity": {
                "version": "context-capacity-v1", "profile_version": "test-v1",
                "provider": "intern", "model": "intern-s2",
                "endpoint": "https://api.example.test/v1/chat/completions",
                "cap_source": "controlled_test", "cap_source_date": "2026-11-07",
                "input_cap_tokens": None, "output_reserve_tokens": 100,
                "safety_margin_tokens": 10,
                "token_estimator_version": "utf8-bytes-per-three-v1",
            },
        }
        with SolverHarness(config=config) as harness:
            run = harness.solve(problem, {"run_id": "s03-context", "problem_spec":
                                          problem_spec(problem, version=7)})
            prepared = harness.prepare_request(run, {
                "role": "whole_solution_verifier", "problem": problem,
                "solution_candidate": "candidate",
            })

        self.assertEqual(7, prepared["problem_spec_version"])
        self.assertEqual(7, prepared["_context_pack"]["specification_version"])
        self.assertEqual(problem, prepared["problem_spec"]["original_problem"])

    def test_one_direction_is_accepted_as_a_step_but_cannot_complete_the_run(self):
        from showcase.solver_harness import ScriptedModelPort, ScriptedVerifierPort

        problem = "Prove both directions."
        spec = problem_spec(problem)
        plan = {"version": 1, "steps": [{
            "step_id": "necessary", "title": "necessary", "objective": "prove necessary",
            "obligation_ids": ["root:necessary"],
        }, {
            "step_id": "sufficient", "title": "sufficient", "objective": "prove sufficient",
            "obligation_ids": ["root:sufficient"], "depends_on": ["necessary"],
        }]}
        with SolverHarness(
            config={**SPEC_CONFIG, "max_model_calls": 4},
            model_port=ScriptedModelPort([
                {"argument": "necessary proof", "claims": [{"statement": "necessary"}]},
                {"argument": "sufficient proof", "claims": [{"statement": "sufficient"}]},
            ]),
            verifier_port=ScriptedVerifierPort([
                {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
                 "obligation_evidence": [{"obligation_id": "root:necessary",
                                           "evidence_category": "universal_proof",
                                           "claim_indexes": [0]}]},
                {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT"},
            ]),
        ) as harness:
            result = harness.solve(problem, {"run_id": "one-direction", "problem_spec": spec,
                                               "plan": plan})

        self.assertEqual("satisfied", result["state"]["obligation_ledger"][0]["status"])
        self.assertEqual("open", result["state"]["obligation_ledger"][1]["status"])
        self.assertEqual("TERMINAL", result["state"]["phase"])
        self.assertEqual("partial_aborted", result["state"]["status"])
        self.assertEqual("ACCEPTED", result["state"]["steps"]["necessary"]["status"])

    def test_step_review_cannot_satisfy_a_root_unmapped_to_its_work_unit(self):
        from showcase.solver_harness import ScriptedModelPort, ScriptedVerifierPort

        problem = "Prove both directions."
        spec = problem_spec(problem)
        plan = {"version": 1, "steps": [{
            "step_id": "necessary", "title": "necessary", "objective": "prove necessary",
            "obligation_ids": ["root:necessary"],
        }, {
            "step_id": "sufficient", "title": "sufficient", "objective": "prove sufficient",
            "obligation_ids": ["root:sufficient"],
        }]}
        model = ScriptedModelPort([
            {"argument": "necessary proof", "claims": [{"statement": "necessary"}]},
            {"argument": "sufficient proof", "claims": [{"statement": "sufficient"}]},
        ])
        verifier = ScriptedVerifierPort([{
            "goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
            "obligation_evidence": [{"obligation_id": "root:sufficient",
                                      "evidence_category": "universal_proof",
                                      "claim_indexes": [0]}],
        }, {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT"}])
        with SolverHarness(
            config={**SPEC_CONFIG, "max_model_calls": 4},
            model_port=model,
            verifier_port=verifier,
        ) as harness:
            result = harness.solve(problem, {"run_id": "unmapped-root-evidence", "problem_spec": spec,
                                               "plan": plan})

        self.assertTrue(all(item["status"] == "open"
                            for item in result["state"]["obligation_ledger"]))
        self.assertEqual("root_obligation_not_mapped_to_work_unit",
                         result["state"]["obligation_evidence_rejections"][0]["reason"])
        self.assertEqual("root_obligations_incomplete", result["state"]["result_reason"])
        self.assertEqual(["reasoner", "reasoner"], [request["role"] for request in model.requests])

    def test_final_step_with_only_one_root_evidence_cannot_enter_finalization(self):
        from showcase.solver_harness import ScriptedModelPort, ScriptedVerifierPort

        problem = "Prove both directions."
        spec = problem_spec(problem)
        plan = {"version": 1, "steps": [{
            "step_id": "joined", "title": "joined", "objective": "prove",
            "obligation_ids": ["root:necessary", "root:sufficient"],
        }]}
        with SolverHarness(
            config={**SPEC_CONFIG, "max_model_calls": 2},
            model_port=ScriptedModelPort([{"argument": "one direction",
                                           "claims": [{"statement": "necessary"}]}]),
            verifier_port=ScriptedVerifierPort([{
                "goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
                "obligation_evidence": [{"obligation_id": "root:necessary",
                                          "evidence_category": "universal_proof",
                                          "claim_indexes": [0]}],
            }]),
        ) as harness:
            result = harness.solve(problem, {"run_id": "incomplete-roots", "problem_spec": spec,
                                               "plan": plan})

        self.assertEqual("TERMINAL", result["state"]["phase"])
        self.assertEqual("partial_aborted", result["state"]["status"])
        self.assertEqual("root_obligations_incomplete", result["state"]["result_reason"])

    def test_complete_roots_reserve_shared_closeout_budget_before_final_calls(self):
        from showcase.run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget
        from showcase.solver_harness import ScriptedModelPort, ScriptedVerifierPort

        problem = "Prove the statement for every integer."
        spec = {
            **problem_spec(problem),
            "root_obligations": [{"obligation_id": "root:universal",
                                  "obligation_type": "universal",
                                  "statement": "The claim holds for every integer."}],
        }
        plan = {"version": 1, "steps": [{
            "step_id": "prove", "title": "prove", "objective": "prove universally",
            "obligation_ids": ["root:universal"],
        }, {
            "step_id": "auxiliary", "title": "auxiliary", "objective": "derive recurrence",
            "auxiliary_goal_ids": ["aux:factor"],
        }]}
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure(
            "closeout", RunBudgetLimits(max_model_calls=8, max_http_attempts=8, max_tokens=100_000)
        )
        with bind_budget(budget), SolverHarness(
            config={**SPEC_CONFIG, "max_model_calls": 8},
            model_port=ScriptedModelPort([
                {"argument": "proof", "claims": [{"statement": "universal proof"}]},
                {"final_response": "Complete answer"},
            ]),
            verifier_port=ScriptedVerifierPort([
                {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
                 "obligation_evidence": [{"obligation_id": "root:universal",
                                           "evidence_category": "universal_proof",
                                           "claim_indexes": [0]}]},
                {"verdict": "ACCEPT"},
            ]),
        ) as harness:
            result = harness.solve(problem, {"run_id": "closeout", "problem_spec": spec,
                                               "plan": plan})

        snapshot = budget.snapshot()
        self.assertEqual("completed_llm_reviewed", result["state"]["status"])
        self.assertEqual("satisfied", result["state"]["obligation_ledger"][0]["status"])
        self.assertEqual("SKIPPED", result["state"]["steps"]["auxiliary"]["status"])
        self.assertEqual(["auxiliary"], [item["work_unit_id"]
                                          for item in result["state"]["skipped_work_units"]])
        self.assertEqual(2, snapshot["logical_calls"])
        self.assertEqual(2, snapshot["http_attempts"])
        self.assertGreater(snapshot["reserved_tokens"], 0)

    def test_closeout_budget_rejection_prevents_final_generation_and_review(self):
        from showcase.run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget
        from showcase.solver_harness import ScriptedModelPort, ScriptedVerifierPort

        problem = "Prove the statement for every integer."
        spec = {
            **problem_spec(problem),
            "root_obligations": [{"obligation_id": "root:universal",
                                  "obligation_type": "universal",
                                  "statement": "The claim holds for every integer."}],
        }
        plan = {"version": 1, "steps": [{
            "step_id": "prove", "title": "prove", "objective": "prove universally",
            "obligation_ids": ["root:universal"],
        }, {
            "step_id": "auxiliary", "title": "auxiliary", "objective": "derive recurrence",
            "auxiliary_goal_ids": ["aux:factor"],
        }]}
        model = ScriptedModelPort([
            {"argument": "proof", "claims": [{"statement": "universal proof"}]},
            {"final_response": "Should not be requested"},
        ])
        verifier = ScriptedVerifierPort([
            {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
             "obligation_evidence": [{"obligation_id": "root:universal",
                                       "evidence_category": "universal_proof",
                                       "claim_indexes": [0]}]},
            {"verdict": "ACCEPT"},
        ])
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure(
            "closeout-blocked",
            RunBudgetLimits(max_model_calls=1, max_http_attempts=4, max_tokens=100_000),
        )
        with bind_budget(budget), SolverHarness(
            config={**SPEC_CONFIG, "max_model_calls": 8},
            model_port=model,
            verifier_port=verifier,
        ) as harness:
            result = harness.solve(problem, {"run_id": "closeout-blocked", "problem_spec": spec,
                                               "plan": plan})

        self.assertEqual("partial_aborted", result["state"]["status"])
        self.assertEqual("run_model_budget_exhausted", result["state"]["result_reason"])
        self.assertEqual(["reasoner"], [request["role"] for request in model.requests])
        self.assertEqual(["step_verifier"], [request["role"] for request in verifier.requests])
        self.assertEqual([], result["state"]["skipped_work_units"])
        self.assertNotEqual("SKIPPED", result["state"]["steps"].get("auxiliary", {}).get("status"))

    def test_specification_change_invalidates_affected_branch_and_keeps_other_evidence(self):
        problem = "Prove both directions."
        spec = problem_spec(problem)
        config = {**SPEC_CONFIG, "features": {**SPEC_CONFIG["features"], "candidate_registry": True}}
        with SolverHarness(config=config) as harness:
            run = harness.solve(problem, {"run_id": "spec-change", "problem_spec": spec})
            plan = {"version": 1, "steps": [
                {"step_id": "necessary", "title": "necessary", "objective": "prove necessary",
                 "obligation_ids": ["root:necessary"]},
                {"step_id": "sufficient", "title": "sufficient", "objective": "prove sufficient",
                 "obligation_ids": ["root:sufficient"]},
            ]}
            evidence = [
                {"evidence_id": "e-necessary", "obligation_id": "root:necessary",
                 "specification_version": 1, "valid": True, "invalidated": False,
                 "source": "necessary"},
                {"evidence_id": "e-sufficient", "obligation_id": "root:sufficient",
                 "specification_version": 1, "valid": True, "invalidated": False,
                 "source": "sufficient"},
            ]
            seeded = harness.commit_event(
                "spec-change", expected_revision=run["state_revision"],
                event={"event_id": "seed-review-state", "type": "fixture_seed"},
                state_updates={
                    "phase": "FINAL_GENERATE", "plan": plan, "plan_version": 1,
                    "steps": {
                        "necessary": {"status": "ACCEPTED", "verification": {
                            "valid": True, "verdict": "ACCEPT"}},
                        "sufficient": {"status": "ACCEPTED", "verification": {
                            "valid": True, "verdict": "ACCEPT"}},
                    },
                    "work_units": [
                        {"work_unit_id": "necessary", "step_id": "necessary",
                         "obligation_ids": ["root:necessary"], "auxiliary_goal_ids": [],
                         "prerequisites": []},
                        {"work_unit_id": "sufficient", "step_id": "sufficient",
                         "obligation_ids": ["root:sufficient"], "auxiliary_goal_ids": [],
                         "prerequisites": []},
                    ],
                    "obligation_evidence_ledger": evidence,
                    "obligation_ledger": [
                        {"obligation_id": "root:necessary", "status": "satisfied",
                         "evidence_refs": ["e-necessary"], "specification_version": 1},
                        {"obligation_id": "root:sufficient", "status": "satisfied",
                         "evidence_refs": ["e-sufficient"], "specification_version": 1},
                    ],
                    "accepted_results": [
                        {"result_id": "r-necessary", "source": "necessary",
                         "statement": "old necessary proof", "dependencies": [],
                         "evidence_level": "llm_reviewed"},
                        {"result_id": "r-sufficient", "source": "sufficient",
                         "statement": "sufficient proof", "dependencies": [],
                         "evidence_level": "llm_reviewed"},
                    ],
                    "candidate_registry": [{
                        "candidate_id": "candidate-old", "version": 1,
                        "review_state": "eligible_unreviewed", "selection_eligible": True,
                        "dependency_refs": ["necessary"], "invalidated_by": [],
                        "evidence_refs": [], "source_event_refs": [],
                    }],
                },
            )
            revised = problem_spec(problem, version=2)
            revised["root_obligations"][0]["statement"] = "Every solution has the required property."
            updated = harness.update_problem_spec(
                "spec-change", expected_revision=seeded["state_revision"], problem_spec=revised
            )
            restored_spec = problem_spec(problem, version=3)
            updated = harness.update_problem_spec(
                "spec-change", expected_revision=updated["state_revision"],
                problem_spec=restored_spec,
            )

        state = updated["state"]
        self.assertEqual(3, state["specification_version"])
        self.assertEqual("PLAN", state["phase"])
        self.assertEqual("open", state["obligation_ledger"][0]["status"])
        self.assertEqual("satisfied", state["obligation_ledger"][1]["status"])
        self.assertTrue(next(item for item in state["obligation_evidence_ledger"]
                             if item["evidence_id"] == "e-necessary")["invalidated"])
        preserved = next(item for item in state["obligation_evidence_ledger"]
                         if item["evidence_id"] == "e-sufficient")
        self.assertEqual([1, 2, 3], preserved["applicable_specification_versions"])
        self.assertEqual("INVALIDATED", state["steps"]["necessary"]["status"])
        self.assertEqual("ACCEPTED", state["steps"]["sufficient"]["status"])
        self.assertEqual("invalidated", state["candidate_registry"][-1]["review_state"])

    def test_specification_update_requires_next_version_and_compare_and_swap(self):
        problem = "Prove both directions."
        with SolverHarness(config=SPEC_CONFIG) as harness:
            run = harness.solve(problem, {"run_id": "spec-cas", "problem_spec": problem_spec(problem)})
            revised = problem_spec(problem, version=2)
            revised["original_problem"] = "Prove both directions under the revised assumptions."
            with self.assertRaises(SolverValidationError):
                harness.update_problem_spec(
                    "spec-cas", expected_revision=run["state_revision"],
                    problem_spec=problem_spec(problem, version=3),
                )
            updated = harness.update_problem_spec(
                "spec-cas", expected_revision=run["state_revision"], problem_spec=revised
            )
            with self.assertRaises(SolverRevisionConflictError):
                harness.update_problem_spec(
                    "spec-cas", expected_revision=run["state_revision"],
                    problem_spec={**revised, "specification_version": 3},
                )
            latest = harness.get_run("spec-cas", problem=problem)
            prepared = harness.prepare_request(latest, {"role": "reasoner", "problem": problem})

        self.assertEqual(updated, latest)
        self.assertEqual(2, latest["state"]["specification_version"])
        self.assertEqual("Prove both directions under the revised assumptions.", prepared["problem"])
        self.assertEqual(2, len(latest["state"]["specification_invalidations"][-1]["affected_obligation_ids"]))

    def test_and_prerequisite_blocks_dependent_work_unit_before_reasoner_dispatch(self):
        from showcase.solver_harness import ScriptedModelPort
        from showcase.storage import SQLiteStore

        problem = "Prove both directions."
        spec = problem_spec(problem)
        plan = {"version": 1, "steps": [
            {"step_id": "first", "title": "first", "objective": "first direction",
             "obligation_ids": ["root:necessary"]},
            {"step_id": "dependent", "title": "dependent", "objective": "second direction",
             "obligation_ids": ["root:sufficient"], "depends_on": ["first"]},
        ]}
        store = SQLiteStore(":memory:")
        self.addCleanup(store.close)
        with SolverHarness(store=store, config=SPEC_CONFIG) as seed:
            run = seed.solve(problem, {"run_id": "blocked-dependent", "problem_spec": spec,
                                       "plan": plan})
            seed.commit_event(
                "blocked-dependent", expected_revision=run["state_revision"],
                event={"event_id": "resume-at-dependent", "type": "fixture_seed"},
                state_updates={"phase": "STEP_EXECUTE", "plan": {
                    "version": 1, "steps": [
                        {"step_id": "first", "title": "first", "objective": "first direction",
                         "obligation_ids": ["root:necessary"]},
                        {"step_id": "dependent", "title": "dependent", "objective": "second direction",
                         "obligation_ids": ["root:sufficient"], "depends_on": ["first"]},
                    ]}, "plan_version": 1, "current_step": "dependent"},
            )
        model = ScriptedModelPort([])
        with SolverHarness(store=store, config=SPEC_CONFIG, model_port=model) as harness:
            result = harness.solve(problem, {"run_id": "blocked-dependent"})

        self.assertEqual("partial_aborted", result["state"]["status"])
        self.assertEqual("work_unit_prerequisites_incomplete", result["state"]["result_reason"])
        self.assertEqual([], model.requests)

    def test_specification_prerequisite_is_added_to_work_unit_and_requires_root_evidence(self):
        from showcase.solver_harness import ScriptedModelPort, ScriptedVerifierPort

        problem = "Prove the lemma before the conclusion."
        spec = problem_spec(problem)
        spec["root_obligations"] = [
            {"obligation_id": "root:lemma", "obligation_type": "universal",
             "statement": "The lemma holds."},
            {"obligation_id": "root:conclusion", "obligation_type": "universal",
             "statement": "The conclusion follows.", "prerequisite_ids": ["root:lemma"]},
        ]
        plan = {"version": 1, "steps": [
            {"step_id": "lemma", "title": "lemma", "objective": "prove lemma",
             "obligation_ids": ["root:lemma"]},
            {"step_id": "conclusion", "title": "conclusion", "objective": "prove conclusion",
             "obligation_ids": ["root:conclusion"]},
        ]}
        model = ScriptedModelPort([
            {"argument": "lemma attempted", "claims": [{"statement": "lemma claim"}]},
            {"argument": "should remain undispatched"},
        ])
        verifier = ScriptedVerifierPort([{
            "goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
        }])
        with SolverHarness(
            config={**SPEC_CONFIG, "max_model_calls": 8},
            model_port=model,
            verifier_port=verifier,
        ) as harness:
            result = harness.solve(problem, {"run_id": "spec-prerequisite", "problem_spec": spec,
                                               "plan": plan})

        self.assertEqual(["lemma"], result["state"]["work_units"][1]["prerequisites"])
        self.assertEqual(["root:lemma"], result["state"]["work_units"][1]["required_obligation_ids"])
        self.assertEqual("open", result["state"]["obligation_ledger"][0]["status"])
        self.assertEqual("work_unit_prerequisites_incomplete", result["state"]["result_reason"])
        self.assertEqual(["reasoner"], [request["role"] for request in model.requests])


if __name__ == "__main__":
    unittest.main()
