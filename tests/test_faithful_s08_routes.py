import unittest

from showcase.solver_harness.aprs import decide, evaluate, pareto_set, verified_gain
from showcase.solver_harness.routes import (
    frontier_digest,
    invalidate_routes,
    plan_frontier,
    register_route,
    transition_route,
    validate_route_frontier,
)


class FaithfulS08RoutesTest(unittest.TestCase):
    def test_frontier_equivalence_is_order_and_duplicate_insensitive(self):
        self.assertEqual(frontier_digest([{"goal": "a"}, {"goal": "b"}, {"goal": "a"}]),
                         frontier_digest([{"goal": "b"}, {"goal": "a"}]))

    def test_frontier_dedup_ignores_step_renames_and_finer_splits_for_same_roots(self):
        spec = {
            "root_obligations": [
                {"obligation_id": "root:a"},
                {"obligation_id": "root:b"},
            ],
            "auxiliary_goals": [],
        }
        left = plan_frontier({"steps": [{"step_id": "old-name", "objective": "one broad task",
                                         "obligation_ids": ["root:a", "root:b"],
                                         "method_id": "direct"}]}, spec)
        right = plan_frontier({"steps": [{"step_id": "piece-1", "objective": "first detail",
                                          "obligation_ids": ["root:a"], "method_id": "direct"},
                                         {"step_id": "piece-2", "objective": "second detail",
                                          "obligation_ids": ["root:b"], "method_id": "direct"}]}, spec)
        self.assertEqual(frontier_digest(left), frontier_digest(right))

    def test_frontier_distinguishes_controlled_methods_for_the_same_root(self):
        spec = {"root_obligations": [{"obligation_id": "root:a"}], "auxiliary_goals": []}
        direct = plan_frontier({"steps": [{"obligation_ids": ["root:a"], "method_id": "direct"}]}, spec)
        induction = plan_frontier({"steps": [{"obligation_ids": ["root:a"], "method_id": "induction"}]}, spec)
        self.assertNotEqual(frontier_digest(direct), frontier_digest(induction))

    def test_route_lineage_allows_one_stalled_alternate_only(self):
        state = {"run_id": "r", "state_revision": 1,
                 "route_policy": {"policy_version": "serial-aprs-v1"}}
        primary = register_route(state, frontier=[{"step_id": "a", "objective": "direct"}])
        state.update(primary)
        state.update(transition_route(state, state["active_route_id"], "stalled", reason="no_progress"))
        alternate = register_route(state, parent_route_id=state["active_route_id"], kind="alternate",
                                   frontier=[{"step_id": "b", "objective": "induction"}],
                                   mutation={"kind": "replace_route"})
        state.update(alternate)
        with self.assertRaisesRegex(ValueError, "alternate_route_limit_reached"):
            register_route(state, parent_route_id=state["active_route_id"], kind="alternate",
                           frontier=[{"step_id": "c"}])
        self.assertEqual("route_", state["route_lineage"][0]["route_id"][:6])

    def test_verified_gain_excludes_duplicates_conjectures_and_invalidated_rows(self):
        state = {"problem_spec": {"specification_version": 2},
                 "obligation_ledger": [
                     {"obligation_id": "root:a", "status": "satisfied", "evidence_refs": ["e1"]},
                     {"obligation_id": "root:b", "status": "satisfied", "evidence_refs": ["e2"]},
                 ],
                 "obligation_evidence_ledger": [
                     {"evidence_id": "e1", "obligation_id": "root:a", "valid": True,
                      "specification_version": 2},
                     {"evidence_id": "e2", "obligation_id": "root:b", "valid": True,
                      "specification_version": 1},
                 ],
                 "verified_results_ledger": [
                     {"result_id": "unrelated-lemma", "category": "Lemma", "valid": True},
                     {"result_id": "guess", "category": "Conjecture", "valid": True},
                 ]}
        self.assertEqual(["root:a"], verified_gain(state))

    def test_aprs_is_deterministic_and_route_selection_is_separate(self):
        state = {"run_id": "r", "state_revision": 1,
                 "route_policy": {"policy_version": "serial-aprs-v1"},
                 "verified_results_ledger": [{"result_id": "lemma", "valid": True,
                                               "category": "Lemma"}], "events": []}
        first = register_route(state, frontier=plan_frontier({"steps": [{"step_id": "a", "objective": "x"}]}))
        state.update(first)
        evaluations = [evaluate(state, state["route_registry"][0])]
        self.assertEqual(pareto_set(evaluations), pareto_set(evaluations))
        decision = decide(state, evaluations)
        self.assertEqual(decision, decide(state, evaluations))
        self.assertEqual("route_", decision["selected_route_id"][:6])
        self.assertTrue(decision["replayable"])

    def test_serial_mode_persists_route_and_public_event_across_restart(self):
        import tempfile
        from pathlib import Path

        from showcase.solver_harness import SolverHarness
        from showcase.solver_harness.routes import sync_plan_route
        from tests.test_faithful_s03_job import SPEC

        config = {"features": {"serial_routes": True, "problem_spec": True,
                               "progress_scheduling": True,
                               "final_generation": True, "final_solution_review": True}}
        plan = {"version": 1, "steps": [{"step_id": "s1", "objective": "direct",
                                            "method_id": "direct",
                                            "obligation_ids": ["root:value"]}]}
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "routes.db"
            with SolverHarness(database_path=db, config=config) as harness:
                run = harness.solve(SPEC["original_problem"],
                                    {"run_id": "route-run", "problem_spec": SPEC})
                run = harness.commit_event("route-run", expected_revision=run["state_revision"],
                                            event={"event_id": "plan", "type": "initial_plan_generated"},
                                            state_updates={"phase": "STEP_EXECUTE", "plan": plan,
                                                           "plan_version": 1, "current_step": "s1"})
                run = sync_plan_route(harness, run)
                self.assertEqual(1, len(run["state"]["route_registry"]))
                self.assertEqual("serial-aprs-v1", run["state"]["route_policy"]["policy_version"])
                revision = run["state_revision"]
                run = sync_plan_route(harness, run)
                self.assertEqual(revision, run["state_revision"])
                self.assertFalse(any(event["type"] == "route_rejected" for event in run["events"]))
            with SolverHarness(database_path=db, config=config) as harness:
                restored = harness.get_run("route-run")
                self.assertEqual(restored["state"]["route_registry"], run["state"]["route_registry"])
                self.assertEqual(1, len(restored["state"]["route_evaluations"]))

    def test_route_mode_does_not_register_an_empty_route_before_plan_exists(self):
        from showcase.solver_harness import SolverHarness
        from tests.test_faithful_s03_job import SPEC

        with SolverHarness(config={"features": {"serial_routes": True, "problem_spec": True,
                                                  "progress_scheduling": True,
                                                  "final_generation": True,
                                                  "final_solution_review": True}}) as harness:
            state = harness.solve(SPEC["original_problem"],
                                  {"run_id": "no-plan", "problem_spec": SPEC})["state"]
        self.assertEqual([], state["route_registry"])

    def test_serial_route_enable_requires_a_frozen_problem_spec(self):
        from showcase.solver_harness import SolverHarness, SolverValidationError

        with SolverHarness(config={"features": {"serial_routes": True,
                                                  "progress_scheduling": True}}) as harness:
            with self.assertRaisesRegex(SolverValidationError, "serial_routes_requires_problem_spec"):
                harness.solve("prove", {"run_id": "routes-without-spec"})

    def test_serial_route_profile_freezes_s04_dependency_and_requires_spec(self):
        from showcase.run_budget import RunBudgetLimits
        from showcase.star_product_config import limited_config

        with self.assertRaisesRegex(ValueError, "serial_routes_requires_problem_spec"):
            limited_config(RunBudgetLimits(), {"serial_routes": True})
        config = limited_config(RunBudgetLimits(), {
            "serial_routes": True, "problem_spec": True,
            "final_generation": True, "final_solution_review": True,
        })
        self.assertIs(True, config["features"]["progress_scheduling"])

    def test_serial_route_rejects_a_plan_without_a_controlled_method(self):
        from showcase.solver_harness import SolverHarness, SolverValidationError
        from tests.test_faithful_s03_job import SPEC

        config = {"features": {"serial_routes": True, "problem_spec": True,
                               "progress_scheduling": True, "final_generation": True,
                               "final_solution_review": True}}
        plan = {"version": 1, "steps": [{"step_id": "s1", "title": "work",
                                          "objective": "work",
                                          "obligation_ids": ["root:value"]}]}
        with SolverHarness(config=config) as harness:
            with self.assertRaisesRegex(SolverValidationError, "route_method_required"):
                harness.solve(SPEC["original_problem"], {
                    "run_id": "route-method-required", "problem_spec": SPEC, "plan": plan,
                })

    def test_unstalled_route_cannot_authorize_alternate_or_silently_continue(self):
        state = {"route_policy": {"enabled": True, "policy_version": "serial-aprs-v1"},
                 "route_registry": [{"route_id": "r1", "kind": "primary", "status": "active",
                                      "frontier_digest": "old"}], "active_route_id": "r1",
                 "progress_policy": {"enabled": True, "version": "progress-v1"},
                 "progress": {"trigger": None},
                 "problem_spec": {"root_obligations": [{"obligation_id": "root:a"}],
                                  "auxiliary_goals": []}}
        self.assertEqual("alternate_requires_stalled_primary", validate_route_frontier(
            state, {"steps": [{"step_id": "renamed", "method_id": "direct", "obligation_ids": ["root:a"]}]}
        ))

    def test_cost_is_minimized_and_unknown_cost_is_preserved(self):
        state = {"run_id": "r", "route_policy": {"policy_version": "serial-aprs-v1"}}
        evaluations = [
            {"route_id": "expensive", "hard_gate": True,
             "vector": {"verified_gain": 1, "evidence_quality": 1, "novelty": 1,
                        "cost": 100, "cost_known": True}},
            {"route_id": "cheap", "hard_gate": True,
             "vector": {"verified_gain": 1, "evidence_quality": 1, "novelty": 1,
                        "cost": 10, "cost_known": True}},
        ]
        self.assertEqual(["cheap"], decide(state, evaluations)["pareto_route_ids"])

    def test_cost_uses_route_consumption_delta_not_remaining_budget(self):
        state = {"run_id": "r", "route_policy": {"policy_version": "serial-aprs-v1"},
                 "route_budget": {"current_snapshot": {
                     "charged_tokens": 500, "http_attempts": 7, "tool_calls": 2,
                     "logical_calls": 9, "tool_wall_time_seconds": 3,
                     "wall_time_seconds": 19, "reserved_tokens": 0,
                     "unknown_attempts": 0, "unresolved_attempts": 0,
                     "unknown_tool_calls": 0,
                 }}}
        from showcase.solver_harness.aprs import evaluate

        spent = evaluate(state, {"route_id": "spent", "status": "stalled",
                                 "budget_at_start": {"charged_tokens": 250, "logical_calls": 4,
                                                     "http_attempts": 3, "tool_calls": 1,
                                                     "tool_wall_time_seconds": 1,
                                                     "wall_time_seconds": 9}})
        cheap = evaluate(state, {"route_id": "cheap", "status": "active",
                                 "budget_at_start": {"charged_tokens": 450, "logical_calls": 8,
                                                     "http_attempts": 6, "tool_calls": 2,
                                                     "tool_wall_time_seconds": 2,
                                                     "wall_time_seconds": 17}})
        self.assertEqual(250, spent["vector"]["cost"])
        self.assertEqual(50, cheap["vector"]["cost"])
        self.assertEqual(["cheap"], decide(state, [spent, cheap])["pareto_route_ids"])

    def test_verified_gain_requires_current_graph_version_evidence(self):
        state = {
            "specification_version": 1,
            "plan_version": 1,
            "attempt_index": 0,
            "proof_graph": {"current_version": 3, "snapshots": [{
                "graph_version": 3,
                "attempts": {
                    "current-attempt": {"result_id": "result-current", "status": "accepted",
                                         "conclusion": "p-current"},
                    "stale-attempt": {"result_id": "result-stale", "status": "invalidated",
                                      "conclusion": "p-stale"},
                },
                "propositions": {
                    "p-current": {"status": "supported", "conflict": False},
                    "p-stale": {"status": "invalidated", "conflict": False},
                },
            }]},
            "obligation_ledger": [{"obligation_id": "root:a", "status": "satisfied",
                                   "evidence_refs": ["e-current", "e-stale"]}],
            "obligation_evidence_ledger": [
                {"evidence_id": "e-current", "obligation_id": "root:a", "valid": True,
                 "specification_version": 1, "source": "step-current",
                 "result_id": "result-current", "plan_version": 1, "attempt_index": 0,
                 "claim_indexes": [0]},
                {"evidence_id": "e-stale", "obligation_id": "root:a", "valid": True,
                 "specification_version": 1, "source": "step-stale",
                 "result_id": "result-stale", "plan_version": 1, "attempt_index": 0,
                 "claim_indexes": [0]},
            ],
            "verified_results_ledger": [
                {"result_id": "result-current", "source": "step-current", "plan_version": 1,
                 "attempt_index": 0, "claim_indexes": [0]},
                {"result_id": "result-stale", "source": "step-stale", "plan_version": 1,
                 "attempt_index": 0, "claim_indexes": [0]},
            ],
        }
        self.assertEqual(["root:a"], verified_gain(state))
        state["obligation_ledger"][0]["evidence_refs"] = ["e-stale"]
        self.assertEqual([], verified_gain(state))

    def test_persisted_aprs_replay_detects_tampered_decisions(self):
        from showcase.solver_harness.aprs import rate_routes, replay_decision

        state = {"run_id": "r", "state_revision": 4,
                 "route_policy": {"policy_version": "serial-aprs-v1"},
                 "route_registry": [{"route_id": "r1", "status": "active",
                                     "frontier_digest": "frontier-1", "frontier": [],
                                     "budget_at_start": {"charged_tokens": 0}}],
                 "route_budget": {"current_snapshot": {"charged_tokens": 3,
                                                          "reserved_tokens": 0,
                                                          "unknown_attempts": 0,
                                                          "unresolved_attempts": 0,
                                                          "unknown_tool_calls": 0}}}
        evaluations, decision = rate_routes(state)
        self.assertTrue(replay_decision(evaluations, decision))
        self.assertFalse(replay_decision(
            evaluations, {**decision, "selected_route_id": "forged"}))

    def test_graph_invalidation_keeps_old_route_version_but_requires_re_evaluation(self):
        state = {"route_registry": [{"route_id": "r1", "graph_version": 1}],
                 "route_invalidations": []}
        patch = invalidate_routes(state, 2)
        self.assertTrue(patch["route_registry"][0]["needs_reevaluation"])
        self.assertEqual("r1", patch["route_invalidations"][-1]["route_ids"][0])

    def test_route_policy_and_history_cannot_be_forged_by_a_generic_state_patch(self):
        from showcase.solver_harness import SolverHarness, SolverValidationError
        from tests.test_faithful_s03_job import SPEC

        with SolverHarness(config={"features": {"serial_routes": True, "problem_spec": True,
                                                  "progress_scheduling": True,
                                                  "final_generation": True,
                                                  "final_solution_review": True}}) as harness:
            run = harness.solve(SPEC["original_problem"],
                                {"run_id": "route-cas", "problem_spec": SPEC})
            forged = {
                "route_registry": [{"route_id": "forged"}],
                "route_lineage": [{"event": "forged"}],
                "route_evaluations": [{"route_id": "forged"}],
                "aprs_decisions": [{"selected_route_id": "forged"}],
                "route_invalidations": [{"route_ids": ["forged"]}],
                "active_route_id": "forged",
                "route_budget": {"expansion_allowed": True},
            }
            for field, value in forged.items():
                run = harness.get_run("route-cas")
                with self.subTest(field=field), self.assertRaises(SolverValidationError):
                    harness.commit_event(
                        "route-cas", expected_revision=run["state_revision"],
                        event={"event_id": f"fake-{field}", "type": "route_created",
                               "route_id": "forged"},
                        state_updates={field: value},
                    )
            self.assertEqual([], harness.get_run("route-cas")["state"]["route_registry"])
