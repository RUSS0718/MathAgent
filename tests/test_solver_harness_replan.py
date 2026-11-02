import unittest

from showcase.solver_harness import ScriptedModelPort, SolverHarness
from showcase.storage import SQLiteStore

PLAN = {"version": 1, "steps": [{"step_id": "s1", "title": "derive", "objective": "bound"}]}
DECISION = {
    "decision": "APPROVE_REPLAN",
    "reason_summary": "route failed",
    "plan_summary": "new route",
    "forbidden_directions": ["search"],
    "reusable_results": [],
    "trace_back_to": None,
}


class ReplanTest(unittest.TestCase):
    def seed(self, harness):
        run = harness.solve("prove", {"run_id": "r"})
        return harness.commit_event(
            "r",
            expected_revision=run["state_revision"],
            event={"event_id": "seed", "type": "seed"},
            state_updates={
                "phase": "META_DECIDE",
                "plan": PLAN,
                "plan_version": 1,
                "current_step": "s1",
                "accepted_results": [
                    {
                        "result_id": "bad",
                        "source": "s1",
                        "dependencies": [],
                        "evidence_level": "llm_reviewed",
                    },
                    {
                        "result_id": "safe",
                        "source": "independent",
                        "dependencies": [],
                        "evidence_level": "tool_verified",
                    },
                    {
                        "result_id": "dependent",
                        "source": "other",
                        "dependencies": ["bad"],
                        "evidence_level": "llm_reviewed",
                    },
                ],
            },
        )

    def test_replacement_is_generated_archived_and_persisted(self):
        planner = ScriptedModelPort([{**PLAN, "version": 2}])
        store = SQLiteStore(":memory:")
        config = {"max_model_calls": 2}
        with SolverHarness(store=store, config=config) as seed:
            self.seed(seed)
        with SolverHarness(
            store=store, config=config, model_port=planner, meta_port=ScriptedModelPort([DECISION])
        ) as harness:
            result = harness.solve("prove", {"run_id": "r"})
            self.assertEqual(2, result["state"]["plan_version"])
            self.assertEqual(1, result["state"]["attempt_index"])
            self.assertEqual(PLAN, result["state"]["failure_records"][-1]["archived_plan"])
            self.assertEqual(result, harness.get_run("r"))
        self.assertEqual("planner", planner.requests[0]["role"])
        self.assertEqual(["search"], planner.requests[0]["forbidden_directions"])
        self.assertEqual(
            ["safe"], [r["result_id"] for r in planner.requests[0]["accepted_results"]]
        )

    def test_reuse_rejects_ambiguous_invalidated_source_but_keeps_exact_safe_id(self):
        safe = {"result_id": "safe", "source": "shared", "statement": "safe",
                "dependencies": [], "evidence_level": "tool_verified"}
        results = [safe, {**safe, "result_id": "ambiguous", "source": "next",
                          "dependencies": ["shared"]},
                   {**safe, "result_id": "exact", "source": "last",
                    "dependencies": ["safe"]}]
        planner = ScriptedModelPort([{**PLAN, "version": 2}])
        store = SQLiteStore(":memory:")
        with SolverHarness(store=store, config={"max_model_calls": 2}) as harness:
            self.seed(harness)
            run = harness.get_run("r")
            harness.commit_event("r", expected_revision=run["state_revision"],
                                 event={"event_id": "invalid-history", "type": "fixture_loaded"},
                                 state_updates={"accepted_results": results,
                                                "failure_records": [{"invalidated_results": [
                                                    {**safe, "result_id": "bad", "statement": "bad"}]}]})
        with SolverHarness(store=store, model_port=planner, meta_port=ScriptedModelPort([DECISION]),
                           config={"max_model_calls": 2}) as harness:
            result = harness.solve("prove", {"run_id": "r"})
            self.assertEqual(result, harness.get_run("r"))
        self.assertEqual(["safe", "exact"],
                         [r["result_id"] for r in planner.requests[0]["accepted_results"]])

    def run_case(self, config, replies):
        store = SQLiteStore(":memory:")
        with SolverHarness(store=store, config=config) as seed:
            self.seed(seed)
        port = ScriptedModelPort(replies)
        with SolverHarness(
            store=store, config=config, model_port=port, meta_port=ScriptedModelPort([DECISION])
        ) as harness:
            result = harness.solve("prove", {"run_id": "r"})
            self.assertEqual(result, harness.get_run("r"))
        return result["state"], port.requests

    def test_no_planner_dispatch_after_meta_spends_last_call(self):
        state, requests = self.run_case({"max_model_calls": 1}, [])
        self.assertEqual([], requests)
        self.assertEqual("model_call_budget_exhausted", state["budget"]["exhaustion_reason"])
        self.assertEqual("TERMINAL", state["phase"])

    def test_invalid_plan_does_not_execute_and_limit_stops_before_planner(self):
        for config, replies, reason in [
            ({"max_model_calls": 3}, [{"version": 2, "steps": []}], "invalid_replacement_plan"),
            ({"max_model_calls": 3, "max_replans": 0}, [], "replan_limit_reached"),
        ]:
            state, requests = self.run_case(config, replies)
            self.assertEqual(reason, state["budget"]["exhaustion_reason"])
            self.assertFalse(any(r["role"] == "reasoner" for r in requests))

    def test_research_is_bounded_noncoding_and_only_unverified(self):
        state, requests = self.run_case(
            {"max_model_calls": 4, "reexplore_after_replan": True, "max_reexploration_tasks": 1},
            [
                {
                    "tasks": [
                        {
                            "prompt": "find counterexample",
                            "permitted_tools": [],
                            "timeout_seconds": 10,
                        },
                        {"prompt": "extra"},
                    ]
                },
                {"finding": "possible bound"},
                {**PLAN, "version": 2},
            ],
        )
        self.assertEqual(["meta", "researcher", "planner"], [r["role"] for r in requests])
        self.assertTrue(all(r["allowed_tools"] == [] for r in requests))
        self.assertEqual(1, len(state["reexploration_tasks"]))
        self.assertEqual([], state["verified_results_ledger"])
        self.assertEqual(
            "unverified_exploration", requests[-1]["reexploration_findings"][0]["provenance"]
        )


class ReplanRulingGateTest(unittest.TestCase):
    """Only the current transition's unconsumed APPROVE_REPLAN ruling archives (ALIGN-AC-14)."""

    def seed_replan(self, meta_decision):
        store = SQLiteStore(":memory:")
        config = {"max_model_calls": 4}
        with SolverHarness(store=store, config=config) as harness:
            run = harness.solve("prove", {"run_id": "r"})
            updates = {
                "phase": "REPLAN", "plan": PLAN, "plan_version": 1,
                "current_step": "s1",
                "meta_decision": None if meta_decision is None else {
                    **meta_decision,
                    "run_id": "r", "plan_version": 1, "attempt_index": 0,
                    "step_id": "s1", "decided_at_revision": run["state_revision"] + 1,
                },
            }
            harness.commit_event(
                "r",
                expected_revision=run["state_revision"],
                event={"event_id": "seed-replan", "type": "seed"},
                state_updates=updates,
            )
        return store, config

    def run_replan(self, store, config, planner_replies):
        planner = ScriptedModelPort(planner_replies)
        with SolverHarness(store=store, config=config, model_port=planner) as harness:
            run = harness.solve("prove", {"run_id": "r"})
            self.assertEqual(run, harness.get_run("r"))
        return run["state"], planner.requests

    def test_missing_or_mismatched_ruling_escalates_instead_of_archiving(self):
        for meta_decision in (None, {**DECISION, "decision": "CONTINUE"}):
            with self.subTest(meta_decision=meta_decision):
                state, requests = self.run_replan(*self.seed_replan(meta_decision), [])
                self.assertEqual([], requests)
                self.assertEqual("META_DECIDE", state["phase"])
                self.assertEqual(1, state["plan_version"])
                self.assertEqual(
                    "UNAUTHORIZED_REPLAN_TRANSITION", state["meta_interventions"][-1]["trigger"]
                )

    def test_consumed_ruling_cannot_archive_again(self):
        consumed = {**DECISION, "consumed": {"event_type": "plan_archived",
                                             "state_revision": 4, "plan_version": 2}}
        state, requests = self.run_replan(*self.seed_replan(consumed), [])
        self.assertEqual([], requests)
        self.assertEqual("META_DECIDE", state["phase"])
        self.assertEqual(1, state["plan_version"])

    def test_valid_ruling_is_consumed_by_the_archive_it_authorizes(self):
        state, requests = self.run_replan(*self.seed_replan(DECISION), [{**PLAN, "version": 2}])
        self.assertEqual(2, state["plan_version"])
        self.assertEqual("planner", requests[0]["role"])
        self.assertEqual(["search"], requests[0]["forbidden_directions"])
        consumption = state["meta_decision"]["consumed"]
        self.assertEqual(("plan_archived", 2),
                         (consumption["event_type"], consumption["plan_version"]))

    def test_replayed_replan_phase_cannot_reuse_the_consumed_ruling(self):
        store, config = self.seed_replan(DECISION)
        state, requests = self.run_replan(store, config, [{**PLAN, "version": 2}])
        self.assertEqual(2, state["plan_version"])
        with SolverHarness(store=store, config=config) as harness:
            run = harness.get_run("r")
            self.assertEqual(2, run["state"]["meta_decision"]["consumed"]["plan_version"])
            # A recovery replays the REPLAN phase against the already-consumed ruling.
            harness.commit_event(
                "r",
                expected_revision=run["state_revision"],
                event={"event_id": "replay-replan", "type": "seed"},
                state_updates={"phase": "REPLAN"},
            )
        replayed, requests_again = self.run_replan(store, config, [])
        self.assertEqual([], requests_again)
        self.assertEqual("META_DECIDE", replayed["phase"])
        self.assertEqual(
            "UNAUTHORIZED_REPLAN_TRANSITION", replayed["meta_interventions"][-1]["trigger"]
        )

    def test_bypassing_the_transition_gate_rearchives_a_consumed_ruling(self):
        from unittest.mock import patch

        from showcase.solver_harness import replan as replan_module

        consumed = {**DECISION, "consumed": {"event_type": "plan_archived",
                                             "state_revision": 4, "plan_version": 2}}
        with patch.object(replan_module, "transition_decision", lambda *arguments: True):
            state, requests = self.run_replan(*self.seed_replan(consumed),
                                              [{**PLAN, "version": 2}])
        # Deliberately bypassing the current-transition gate lets the consumed
        # ruling archive again: the exact regression the consumption contract blocks.
        self.assertEqual(2, state["plan_version"])
        self.assertEqual("planner", requests[0]["role"])
