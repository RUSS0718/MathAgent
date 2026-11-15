"""Planner wire examples stay executable under the active autonomous schema."""

import json
import unittest
from copy import deepcopy

from showcase.adapters import InternModelAdapter
from showcase.run_budget import RunBudgetLedger
from showcase.solver_harness import SolverHarness
from showcase.solver_harness.autonomous_routes import planner_request
from showcase.solver_harness.intern_port import InternModelPort, InternPortError
from showcase.solver_harness.intern_schemas import response_schema
from showcase.solver_harness.protocol_repair import REPAIR_INSTRUCTION
from showcase.solver_harness.specification import bind_plan_work_units
from showcase.tool_schemas import schema_error
from tests.test_solver_harness_intern import FakeClient


class AutonomousPlannerExamplesTest(unittest.TestCase):
    def _transport_examples(self, request):
        before = deepcopy(request)
        client = FakeClient([{"content": "{}", "finish_reason": "stop"}])
        port = InternModelPort(adapter=InternModelAdapter(client=client))
        with self.assertRaises(InternPortError) as caught:
            port.complete(request)
        self.assertEqual("invalid_role_schema", caught.exception.category)
        self.assertEqual(before, request)
        self.assertEqual(1, len(client.requests))
        system = client.requests[0][0][0]["content"]
        marker = "Illustrative instances " if request.get("autonomous_routes") else "Illustrative instance "
        examples = json.loads(system.split(marker, 1)[1].split(": ", 1)[1])
        return examples if isinstance(examples, list) else [examples], system

    def _assert_bound_examples(self, request, examples, expected_edges, statements):
        roots = {item["obligation_id"] for item in request["problem_spec"]["root_obligations"]}
        for example in examples:
            self.assertIsNone(schema_error(example, response_schema(request)))
            self.assertEqual(request.get("plan_version", 1), example["plan"]["version"])
            for plan in [example["plan"], *example["plan"].get("alternative_plans", [])]:
                bind_plan_work_units(plan, request["problem_spec"])
                owners = {}
                for index, step in enumerate(plan["steps"]):
                    ids = step["obligation_ids"] + step["auxiliary_goal_ids"]
                    self.assertEqual(1, len(ids))
                    objective_id = ids[0]
                    self.assertNotIn(objective_id, owners)
                    owners[objective_id] = (index, step)
                    self.assertEqual(statements[objective_id], step["objective"])
                    self.assertEqual([objective_id] if objective_id in roots else [], step["obligation_ids"])
                    self.assertEqual([] if objective_id in roots else [objective_id], step["auxiliary_goal_ids"])
                self.assertEqual(set(expected_edges), set(owners))
                for objective_id, prerequisites in expected_edges.items():
                    index, step = owners[objective_id]
                    self.assertEqual({owners[item][1]["step_id"] for item in prerequisites},
                                     set(step["depends_on"]))
                    for prerequisite in prerequisites:
                        self.assertLess(owners[prerequisite][0], index)

    def test_public_examples_bind_current_graph_and_explicit_edges_in_both_modes(self):
        from showcase.solver_harness.population_runtime import prepare_population_plan

        spec = {"specification_version": 3, "original_problem": "Establish the declared claims",
            "domain": "integers", "quantifiers": [], "assumptions": [],
            "directions": [], "output_requirements": [], "root_obligations": [
                {"obligation_id": "root:finish", "obligation_type": "universal",
                 "statement": "Establish the final claim", "prerequisite_ids": ["aux:bridge"]},
                {"obligation_id": "root:middle", "obligation_type": "universal",
                 "statement": "Establish the middle claim", "prerequisite_ids": ["root:start"]},
                {"obligation_id": "root:start", "obligation_type": "universal",
                 "statement": "Establish the initial claim", "prerequisite_ids": ["aux:prepare"]}],
            "auxiliary_goals": [
                {"goal_id": "aux:optional", "description": "An unneeded consequence",
                 "dependencies": ["root:finish"]},
                {"goal_id": "aux:bridge", "description": "Establish the bridge",
                 "dependencies": ["root:middle", "aux:prepare"]},
                {"goal_id": "aux:prepare", "description": "Establish the prerequisite", "dependencies": []}]}
        request = {"role": "planner", "problem": spec["original_problem"], "problem_spec": spec,
            "plan_version": 2, "checkpoint_protocol": True, "progress_policy": {"enabled": True},
            "autonomous_routes": {"capacity": {"max_inflight": 2, "worker_slots": 2}}}
        edges = {"aux:prepare": [], "root:start": ["aux:prepare"], "root:middle": ["root:start"],
                 "aux:bridge": ["root:middle", "aux:prepare"], "root:finish": ["aux:bridge"]}
        statements = {"aux:prepare": "Establish the prerequisite", "root:start": "Establish the initial claim",
            "root:middle": "Establish the middle claim", "aux:bridge": "Establish the bridge",
            "root:finish": "Establish the final claim"}
        for repair in (False, True):
            with self.subTest(repair=repair):
                current = {**request, **({"repair_instruction": REPAIR_INSTRUCTION} if repair else {})}
                examples, system = self._transport_examples(current)
                self.assertEqual(["serial", "population"],
                                 [item["plan"]["execution_selection"]["mode"] for item in examples])
                self._assert_bound_examples(current, examples, edges, statements)
                self.assertIn("equally valid shapes, not mode recommendations", system)
                self.assertIn("not mathematical method recommendations", system)
                population = examples[1]["plan"]
                self.assertEqual(1, population["alternative_plans"][0]["version"])
                self.assertNotEqual(prepare_population_plan(population, spec)[1],
                    prepare_population_plan(population["alternative_plans"][0], spec)[1])

    def test_single_root_examples_keep_current_statement_without_required_method(self):
        spec = {"specification_version": 1, "original_problem": "Prove the claim", "domain": "reals",
            "quantifiers": [], "assumptions": [], "directions": [], "output_requirements": [],
            "root_obligations": [{"obligation_id": "root:single", "obligation_type": "universal",
                                  "statement": "Prove the claim"}], "auxiliary_goals": []}
        request = {"role": "planner", "problem": spec["original_problem"], "problem_spec": spec,
                   "checkpoint_protocol": True}
        examples, _ = self._transport_examples(request)
        self.assertEqual(1, len(examples))
        self._assert_bound_examples(request, examples, {"root:single": []}, {"root:single": "Prove the claim"})
        self.assertNotIn("method_id", examples[0]["plan"]["steps"][0])

    def test_without_spec_retains_fictional_shape_example(self):
        request = {"role": "planner", "problem": "Prove a claim", "checkpoint_protocol": True}
        examples, system = self._transport_examples(request)
        self.assertEqual(1, len(examples))
        self.assertIn("fictional IDs only", system)
        self.assertIsNone(schema_error(examples[0], response_schema(request)))
        self.assertEqual(["Prove A", "Derive B using A"],
                         [step["objective"] for step in examples[0]["plan"]["steps"]])
        self.assertEqual([[], ["S1"]], [step["depends_on"] for step in examples[0]["plan"]["steps"]])

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
