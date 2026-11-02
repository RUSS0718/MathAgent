"""Public Planner checkpoint handoff contracts for CP-03."""

import unittest

from showcase.solver_harness import ScriptedModelPort, SolverHarness
from showcase.solver_harness.intern_schemas import response_schema
from showcase.tool_schemas import schema_error


FEATURES = {
    "final_generation": True,
    "planner_checkpoints": True,
    "stream_recovery": True,
}


def checkpoint(status="YIELD", *, marker="draft-a", version=1):
    return {
        "protocol_version": version,
        "status": status,
        "objective": "derive the result",
        "dependencies": ["known fact"],
        "evidence": [marker],
        "gaps": ["complete the final implication"],
        "next_action": "close the remaining gap",
        "checkpoint_id": marker,
    }


class PlannerCheckpointTest(unittest.TestCase):
    def test_yield_feedback_then_final_plan_uses_new_identity(self):
        plan = {
            "version": 1,
            "steps": [{"step_id": "s1", "title": "proof", "objective": "derive"}],
        }
        port = ScriptedModelPort([
            {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []},
            {"checkpoint": checkpoint()},
            {"checkpoint": {**checkpoint("FINAL"), "plan": plan}},
            {"argument": "draft proof", "claims": [], "blocked": False},
        ])
        with SolverHarness(
            config={"features": FEATURES, "max_model_calls": 4}, model_port=port
        ) as harness:
            result = harness.solve("question", {"run_id": "planner-checkpoint"})

        self.assertEqual(plan, result["state"]["plan"])
        self.assertEqual("STEP_VERIFY", result["state"]["phase"])
        checkpoints = result["state"]["planner_checkpoints"]
        self.assertEqual(1, len(checkpoints))
        self.assertEqual("YIELD", checkpoints[0]["status"])
        self.assertTrue(checkpoints[0]["parent_checkpoint_id"] is None)
        planner_requests = [item for item in port.requests if item["role"] == "planner"]
        self.assertEqual(2, len(planner_requests))
        self.assertNotEqual(planner_requests[0]["call_id"], planner_requests[1]["call_id"])
        self.assertEqual(checkpoints[0]["checkpoint_id"], planner_requests[1]["parent_checkpoint_id"])
        self.assertEqual("close the remaining gap", planner_requests[1]["feedback"]["next_action"])

    def test_invalid_checkpoint_version_and_duplicate_progress_stop(self):
        invalid = ScriptedModelPort([
            {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []},
            {"checkpoint": checkpoint(version=0)},
        ])
        with SolverHarness(
            config={"features": FEATURES, "max_model_calls": 3}, model_port=invalid
        ) as harness:
            rejected = harness.solve("question", {"run_id": "bad-checkpoint"})
        self.assertEqual("TERMINAL", rejected["state"]["phase"])
        self.assertEqual("invalid_planner_checkpoint", rejected["state"]["result_reason"])
        self.assertEqual(2, len(invalid.requests))

        repeated = ScriptedModelPort([
            {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []},
            {"checkpoint": checkpoint()},
            {"checkpoint": checkpoint()},
        ])
        with SolverHarness(
            config={"features": FEATURES, "max_model_calls": 4}, model_port=repeated
        ) as harness:
            stopped = harness.solve("question", {"run_id": "repeat-checkpoint"})
        self.assertEqual("TERMINAL", stopped["state"]["phase"])
        self.assertEqual("planner_checkpoint_no_progress", stopped["state"]["result_reason"])
        self.assertEqual(3, len(repeated.requests))

    def test_disabled_feature_keeps_existing_planner_contract(self):
        plan = {
            "version": 1,
            "steps": [{"step_id": "s1", "title": "proof", "objective": "derive"}],
        }
        port = ScriptedModelPort([
            {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []},
            plan,
            {"argument": "draft proof", "claims": [], "blocked": False},
        ])
        with SolverHarness(
            config={"features": {"final_generation": True}, "max_model_calls": 3},
            model_port=port,
        ) as harness:
            result = harness.solve("question", {"run_id": "planner-disabled"})
        self.assertEqual(plan, result["state"]["plan"])
        self.assertNotIn("planner_checkpoints", result["state"])

    def test_checkpoint_schema_accepts_nested_final_plan_and_requires_identity(self):
        plan = {
            "version": 1,
            "steps": [{"step_id": "s1", "title": "proof", "objective": "derive"}],
        }
        schema = response_schema({"role": "planner", "checkpoint_protocol": True})
        final = {"checkpoint": {**checkpoint("FINAL"), "plan": plan}}
        self.assertIsNone(schema_error(final, schema))

        missing_yield_id = {"checkpoint": checkpoint("FINAL")}
        missing_yield_id["checkpoint"].pop("checkpoint_id")
        self.assertEqual("tool_schema_invalid", schema_error(missing_yield_id, schema))
