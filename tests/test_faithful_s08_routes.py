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
        left = plan_frontier({"steps": [{"step_id": "old-name", "objective": "one broad task",
                                         "obligation_ids": ["root:a", "root:b"]}]})
        right = plan_frontier({"steps": [{"step_id": "piece-1", "objective": "first detail",
                                          "obligation_ids": ["root:a"]},
                                         {"step_id": "piece-2", "objective": "second detail",
                                          "obligation_ids": ["root:b"]}]})
        self.assertEqual(frontier_digest(left), frontier_digest(right))

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

        config = {"features": {"serial_routes": True}}
        plan = {"version": 1, "steps": [{"step_id": "s1", "objective": "direct",
                                            "obligation_ids": ["root:direct"]}]}
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "routes.db"
            with SolverHarness(database_path=db, config=config) as harness:
                run = harness.solve("prove", {"run_id": "route-run"})
                run = harness.commit_event("route-run", expected_revision=run["state_revision"],
                                            event={"event_id": "plan", "type": "initial_plan_generated"},
                                            state_updates={"phase": "STEP_EXECUTE", "plan": plan,
                                                           "plan_version": 1, "current_step": "s1"})
                run = sync_plan_route(harness, run)
                self.assertEqual(1, len(run["state"]["route_registry"]))
                self.assertEqual("serial-aprs-v1", run["state"]["route_policy"]["policy_version"])
            with SolverHarness(database_path=db, config=config) as harness:
                restored = harness.get_run("route-run")
                self.assertEqual(restored["state"]["route_registry"], run["state"]["route_registry"])
                self.assertTrue(any(e["type"] == "route_created" for e in restored["events"]))

    def test_route_mode_does_not_register_an_empty_route_before_plan_exists(self):
        from showcase.solver_harness import SolverHarness

        with SolverHarness(config={"features": {"serial_routes": True}}) as harness:
            state = harness.solve("prove", {"run_id": "no-plan"})["state"]
        self.assertEqual([], state["route_registry"])

    def test_unstalled_route_cannot_authorize_alternate_or_silently_continue(self):
        state = {"route_policy": {"enabled": True, "policy_version": "serial-aprs-v1"},
                 "route_registry": [{"route_id": "r1", "kind": "primary", "status": "active",
                                      "frontier_digest": "old"}], "active_route_id": "r1",
                 "progress": {"trigger": None}}
        self.assertEqual("alternate_requires_stalled_primary", validate_route_frontier(
            state, {"steps": [{"step_id": "renamed", "obligation_ids": ["root:a"]}]}
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

    def test_graph_invalidation_keeps_old_route_version_but_requires_re_evaluation(self):
        state = {"route_registry": [{"route_id": "r1", "graph_version": 1}],
                 "route_invalidations": []}
        patch = invalidate_routes(state, 2)
        self.assertTrue(patch["route_registry"][0]["needs_reevaluation"])
        self.assertEqual("r1", patch["route_invalidations"][-1]["route_ids"][0])

    def test_route_policy_and_history_cannot_be_forged_by_a_generic_state_patch(self):
        from showcase.solver_harness import SolverHarness, SolverValidationError

        with SolverHarness(config={"features": {"serial_routes": True}}) as harness:
            run = harness.solve("prove", {"run_id": "route-cas"})
            with self.assertRaises(SolverValidationError):
                harness.commit_event(
                    "route-cas", expected_revision=run["state_revision"],
                    event={"event_id": "fake-route", "type": "fixture_seed"},
                    state_updates={"route_registry": [{"route_id": "forged"}],
                                   "route_lineage": [{"event": "forged"}]},
                )
            self.assertEqual([], harness.get_run("route-cas")["state"]["route_registry"])
