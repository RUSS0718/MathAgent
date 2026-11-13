"""Planner wire examples stay executable under the active autonomous schema."""

import json
import unittest
from copy import deepcopy

from showcase.run_budget import RunBudgetLedger
from showcase.solver_harness import SolverHarness
from showcase.solver_harness.autonomous_routes import planner_request
from showcase.solver_harness.intern_port import InternModelPort
from showcase.solver_harness.intern_schemas import response_schema
from showcase.solver_harness.protocol_repair import REPAIR_INSTRUCTION
from showcase.tool_schemas import schema_error


class AutonomousPlannerExamplesTest(unittest.TestCase):
    def test_initial_and_repair_requests_show_balanced_schema_valid_top_level_plans(self):
        request = {"role": "planner", "problem": "Prove A, then derive B using A",
            "checkpoint_protocol": True, "progress_policy": {"enabled": True},
            "problem_spec": {"root_obligations": [
                {"obligation_id": "example:A"},
                {"obligation_id": "example:B", "prerequisite_ids": ["example:A"]},
            ], "auxiliary_goals": []}}
        run = {"run_id": "example-run", "state": {"autonomous_routes": {
            "version": "autonomous-routes-v1", "population_policy": {
                "capacity": {"max_inflight": 2, "worker_slots": 2}}}}}
        with SolverHarness() as harness:
            RunBudgetLedger(harness._state_store._connection).close()
            request = planner_request(harness, run, request)
        self.assertIn("top-level plan", request["instruction"])
        self.assertNotIn("checkpoint.plan for checkpoint replies", request["instruction"])
        for repair in (False, True):
            with self.subTest(repair=repair):
                current = {**request, **({"repair_instruction": REPAIR_INSTRUCTION} if repair else {})}
                schema = response_schema(current)
                messages = InternModelPort()._messages(current, schema)
                system = messages[0]["content"]
                self.assertFalse(json.dumps(schema, ensure_ascii=False) in system,
                                 "Autonomous checkpoint instructions must use the compact data contract")
                examples = json.loads(system.split("Illustrative instances ", 1)[1].split(": ", 1)[1])
                self.assertIn("required and additionalProperties are schema metadata, never output fields", system)
                self.assertEqual({"serial", "population"},
                                 {item["plan"]["execution_selection"]["mode"] for item in examples})
                self.assertEqual(2, len(examples))
                for example in examples:
                    self.assertIsNone(schema_error(example, schema))
                    self.assertNotIn("plan", example["checkpoint"])
                    plan = example["plan"]
                    alternatives = plan["alternative_plans"]
                    self.assertEqual(0 if plan["execution_selection"]["mode"] == "serial" else 1,
                                     len(alternatives))
                    for alternative in alternatives:
                        self.assertNotIn("execution_selection", alternative)
                        self.assertEqual({"example:A", "example:B"}, {
                            root for step in alternative["steps"] for root in step["obligation_ids"]})
                    for location in ("root", "checkpoint"):
                        polluted = deepcopy(example)
                        target = polluted if location == "root" else polluted["checkpoint"]
                        target.update(required=[], additionalProperties=False)
                        self.assertIsNotNone(schema_error(polluted, schema))
                    misplaced = deepcopy(example)
                    misplaced["status"] = misplaced["checkpoint"].pop("status")
                    misplaced["gaps"] = misplaced["checkpoint"]["gaps"]
                    self.assertIsNotNone(schema_error(misplaced, schema))
