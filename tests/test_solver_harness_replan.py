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
