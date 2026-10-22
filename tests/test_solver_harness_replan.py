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
