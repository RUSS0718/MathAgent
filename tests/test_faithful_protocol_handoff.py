"""Real port messages and public Jobs cover the failed live handoff boundaries."""

import hashlib
import json
import os
import sqlite3
import unittest
from contextlib import closing
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import requests

from llm_client import InternChatClient
from showcase.adapters import InternStreamAdapter
from showcase.run_budget import RunBudgetLimits
from showcase.solver_harness.intern_port import InternModelPort
from showcase.solver_harness.intern_schemas import response_schema
from showcase.star_product_config import CORE_FEATURES
from showcase.tool_schemas import schema_error
from tests.controlled_stream_profiles import configure_controlled_streaming
from tests.star_product_support import ACCEPT, POLISH, SOLVED, RawProviderContent, StarJobFixture
from tests.test_faithful_s03_job import CAPACITY_POLICY, ENDPOINT, SPEC
from tests.test_solver_harness_planner_checkpoint import checkpoint as planner_checkpoint
from tests.test_solver_harness_reasoner_checkpoint import checkpoint as reasoner_checkpoint


class PlannerHandoffMessagesTest(unittest.TestCase):
    def test_runtime_usage_is_separate_from_the_strict_provider_checkpoint(self):
        from showcase.solver_harness.reasoner_checkpoint import parse

        reply = reasoner_checkpoint("FINAL")
        envelope = {**reply, "usage": {"total_tokens": 10}}
        schema = response_schema({"role": "reasoner", "checkpoint_protocol": True})
        self.assertIsNotNone(schema_error(envelope, schema))
        self.assertEqual(reply["checkpoint"], parse(envelope))
        with self.assertRaises(ValueError):
            parse({**envelope, "invented": True})

    def test_reasoner_provider_schema_matches_checkpoint_status_and_gap_rules(self):
        from showcase.solver_harness.reasoner_checkpoint import parse

        schema = response_schema({"role": "reasoner", "checkpoint_protocol": True})
        for status in ("YIELD", "FINAL", "BLOCKED", "FAILED"):
            for gaps in ([], ["current-step gap"]):
                reply = reasoner_checkpoint(status)
                reply["checkpoint"]["gaps"] = gaps
                valid = not ((status == "YIELD" and not gaps) or (status == "FINAL" and gaps))
                with self.subTest(status=status, gaps=gaps):
                    self.assertEqual(valid, schema_error(reply, schema) is None)
                    if valid:
                        self.assertEqual(status, parse(reply)["status"])
                    else:
                        with self.assertRaises(ValueError):
                            parse(reply)

    def request(self):
        spec = deepcopy(SPEC)
        spec["root_obligations"].append({
            "obligation_id": "root:explain", "obligation_type": "universal",
            "statement": "Explain the value", "prerequisite_ids": ["root:value"],
        })
        return {"role": "planner", "problem": "1+1", "problem_spec": spec,
                "checkpoint_protocol": True}

    def test_schema_rejects_foreign_objective_ids_before_binding(self):
        request = self.request()
        plan = {"version": 1, "steps": [{"step_id": "s", "title": "Add",
                "objective": "Compute", "obligation_ids": ["invented"], "auxiliary_goal_ids": []}]}
        schema = response_schema(request)["properties"]["plan"]["oneOf"][0]
        self.assertIsNotNone(schema_error(plan, schema))
        plan["steps"][0]["obligation_ids"] = ["root:value", "root:explain"]
        self.assertIsNone(schema_error(plan, schema))

    def test_planner_receives_dependency_table_and_one_unambiguous_example(self):
        request = self.request()
        messages = InternModelPort()._messages(request, response_schema(request))
        context = json.loads(messages[-1]["content"])
        self.assertEqual([
            {"objective_id": "root:value", "kind": "root", "prerequisite_ids": []},
            {"objective_id": "root:explain", "kind": "root", "prerequisite_ids": ["root:value"]},
        ], context.get("objective_dependencies"))
        system = messages[0]["content"]
        self.assertIn("FINAL means the Plan is ready for the Reasoner", system)
        self.assertNotIn("completion of the whole Step", system)
        self.assertNotIn("polynomial_check accepts", system)
        self.assertIn("Illustrative instance", system)

    def test_intake_receives_task_scope_without_reviewer_tool_instructions(self):
        request = {"role": "problem_intake", "problem": "1+1"}
        system = InternModelPort()._messages(request, response_schema(request))[0]["content"]
        self.assertIn("not workflow stages", system)
        self.assertIn("Do not duplicate a root obligation", system)
        self.assertIn("minimum or maximum", system)
        self.assertNotIn("polynomial_check accepts", system)
        self.assertNotIn("provisional enum verdict", system)

    def test_planner_and_reviewer_distinguish_preparation_from_proof(self):
        request = self.request()
        system = InternModelPort()._messages(request, response_schema(request))[0]["content"]
        self.assertIn("Pure preparation", system)
        request = {"role": "step_verifier", "problem": "1+1", "problem_spec": SPEC,
                   "step_goal": "Choose a method before deriving the proof"}
        system = InternModelPort()._messages(request, response_schema(request))[0]["content"]
        self.assertIn("omit answer_claim", system)
        self.assertIn("not a generic review summary", system)
        self.assertIn("never mark an unproved claim as Lemma", system)

    def test_planner_output_itself_satisfies_the_request_for_a_separate_plan(self):
        request = self.request()
        system = InternModelPort()._messages(request, response_schema(request))[0]["content"]
        self.assertIn("Your returned Plan itself", system)
        self.assertIn("Do not schedule producing another plan", system)

    def test_planner_wire_method_uses_the_existing_controller_vocabulary(self):
        request = self.request()
        request["progress_policy"] = {"enabled": True}
        schema = response_schema(request)["properties"]["plan"]["oneOf"][0]
        plan = {"version": 1, "steps": [{"step_id": "S1", "title": "Check", "objective": "Check",
            "obligation_ids": ["root:value", "root:explain"], "auxiliary_goal_ids": [], "method_id": "verification"}]}
        self.assertIsNotNone(schema_error(plan, schema))
        for method in ("direct", "computation", "unknown"):
            plan["steps"][0]["method_id"] = method
            self.assertIsNone(schema_error(plan, schema))

    def test_obligation_evidence_wire_labels_match_the_existing_root_contract(self):
        spec = deepcopy(SPEC)
        spec["root_obligations"][0]["obligation_type"] = "existence"
        schema = response_schema({"role": "step_verifier", "problem_spec": spec})
        reply = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": "",
                 "obligation_evidence": [{"obligation_id": "root:value", "evidence_category": "Computation",
                                          "claim_indexes": [0]}]}
        self.assertIsNotNone(schema_error(reply, schema))
        reply["obligation_evidence"][0]["evidence_category"] = "existence_witness"
        self.assertIsNone(schema_error(reply, schema))
        reply["obligation_evidence"][0]["obligation_id"] = "foreign"
        self.assertIsNotNone(schema_error(reply, schema))
        for empty_spec in ({}, {"root_obligations": []}):
            empty_schema = response_schema({"role": "step_verifier", "problem_spec": empty_spec})
            self.assertIsNotNone(schema_error(reply, empty_schema))
            self.assertIsNone(schema_error({**reply, "obligation_evidence": []}, empty_schema))

    def test_step_review_exposes_only_mapped_objectives_as_its_completion_scope(self):
        request = {**self.request(), "role": "step_verifier", "step_goal": "Compute the value",
                   "step": {"objective": "Compute the value", "obligation_ids": ["root:value"],
                            "auxiliary_goal_ids": []}}
        schema = response_schema(request)
        messages = InternModelPort()._messages(request, schema)
        scope = json.loads(messages[-1]["content"]).get("step_review_scope")
        self.assertEqual({"objective": "Compute the value", "root_obligations": [SPEC["root_obligations"][0]],
                          "auxiliary_goals": []}, scope)
        reply = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": "",
                 "obligation_evidence": [{"obligation_id": "root:explain",
                    "evidence_category": "universal_proof", "claim_indexes": [0]}]}
        self.assertIsNotNone(schema_error(reply, schema))
        reply["obligation_evidence"][0]["obligation_id"] = "root:value"
        self.assertIsNone(schema_error(reply, schema))
        request["step"]["obligation_ids"] = []
        self.assertIsNotNone(schema_error(reply, response_schema(request)))


class FaithfulProtocolHandoffTest(StarJobFixture, unittest.TestCase):
    def open_faithful(self, replies, *, calls=8, stream=False, stream_requests=(), registry=None):
        self.enterContext(patch.dict(os.environ, {"INTERN_API_BASE": ENDPOINT}))
        adapter = {}
        if stream:
            port = InternStreamAdapter(InternChatClient(retry=1), max_tokens=256)
            profiles = configure_controlled_streaming(port)
            shape = (("system", ("content", "role")),) * 4 + (("user", ("content", "role")),)
            profiles = [replace(profile, messages_schema=shape) for profile in profiles]
            for request in stream_requests:
                encoded = json.dumps(response_schema(request), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
                profiles.append(replace(profiles[0], schema_fingerprint=hashlib.sha256(encoded.encode()).hexdigest()))
            adapter = {"SHOWCASE_STAR_ADAPTER": port, "SHOWCASE_STAR_TRANSPORT_POLICY": "stream_first",
                       "SHOWCASE_STAR_TRANSPORT_PROFILES": tuple(profiles)}
        if registry is not None:
            adapter["SHOWCASE_STAR_REGISTRY"] = registry
        self.open_star(replies, **adapter, stream_chunk_size=256, SHOWCASE_FAITHFUL_AUTONOMOUS=True,
            SHOWCASE_STAR_FULL_ENABLED=True,
            SHOWCASE_STAR_FULL_FEATURES=dict.fromkeys(CORE_FEATURES | {
                "auto_problem_spec", "problem_spec", "context_pack", "proof_graph",
                "progress_scheduling", "serial_routes", "planner_checkpoints", "reasoner_checkpoints"}
                | ({"stream_activity"} if stream else set()), True),
            SHOWCASE_STAR_CONTEXT_CAPACITY=CAPACITY_POLICY,
            SHOWCASE_STAR_FULL_BUDGET=RunBudgetLimits(max_model_calls=calls, max_http_attempts=calls))
        pipeline = self.app.extensions["showcase_workspace_service"].star_pipeline
        self.enterContext(patch.object(pipeline, "full_gaps", return_value=[]))

    def submit(self):
        response = self.client.post("/api/agent/jobs", headers=self.headers(),
                                    json={"message": "1+1", "session_id": self.session})
        self.assertEqual(202, response.status_code, response.get_json())
        return response.get_json()["job_id"]

    def test_intake_typo_uses_one_metered_repair_with_exact_failed_reply(self):
        bad = deepcopy(SPEC)
        bad["directionions"] = bad.pop("directions")
        self.open_faithful([bad, SPEC, SOLVED, POLISH, ACCEPT])
        job_id = self.submit()
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"])
        intake = [request for request in self.outbound if request["role"] == "problem_intake"]
        self.assertEqual(2, len(intake))
        self.assertEqual(intake[0]["call_id"] + ":repair-1", intake[1]["call_id"])
        repair = intake[1]["format_repair"]
        self.assertEqual(bad, json.loads(repair["previous_response"]))
        self.assertIn({"path": "$.directions", "message": "required"}, repair["schema_errors"])
        self.assertEqual(5, final["result"]["budget"]["http_attempts"])
        before = deepcopy(final["result"]["request_attempts"])
        self.assertEqual(before, self.job(job_id)["result"]["request_attempts"])
        self.assertEqual(5, len(self.outbound))

    def test_intake_repeated_protocol_failure_stops_after_two_calls(self):
        self.open_faithful([{"bad": True}, {"bad": True}])
        job_id = self.submit()
        final = self.terminal(job_id)
        self.assertEqual("failed", final["status"])
        self.assertEqual("protocol_failure_unrepaired", final["result"]["solver"]["result_reason"])
        self.job(job_id)
        self.assertEqual(["problem_intake"] * 2, [r["role"] for r in self.outbound])

    def test_intake_protocol_repair_does_not_bypass_root_budget(self):
        self.open_faithful([{"bad": True}], calls=1)
        final = self.terminal(self.submit())
        self.assertEqual("failed", final["status"])
        self.assertEqual(1, len(self.outbound))
        self.assertEqual(1, final["result"]["budget"]["http_attempts"])

    def test_intake_unknown_never_starts_protocol_repair(self):
        self.open_faithful([requests.ReadTimeout("unknown remote intake")])
        job_id = self.submit()
        final = self.terminal(job_id)
        self.assertEqual("failed", final["status"])
        self.assertEqual(1, len(final["result"]["solver"]["recovery"]["unknown_calls"]))
        self.job(job_id)
        self.assertEqual(1, len(self.outbound))

    def test_explore_schema_repair_receives_the_actual_failed_instance(self):
        bad = {"assessment": "NEED_PLAN", "failed": [], "candidates": []}
        self.open_faithful([SPEC, RawProviderContent(json.dumps(bad)), SOLVED, POLISH, ACCEPT])
        final = self.terminal(self.submit())
        self.assertEqual("succeeded", final["status"])
        explore = [request for request in self.outbound if request["role"] == "explore"]
        self.assertEqual(2, len(explore))
        repair = explore[1].get("format_repair", {})
        self.assertEqual(bad, json.loads(repair.get("previous_response", "{}")))
        self.assertIn({"path": "$.worked", "message": "required"}, repair.get("schema_errors", []))

    def test_binding_feedback_identifies_objective_and_its_self_owned_prerequisite(self):
        spec = deepcopy(SPEC)
        spec["auxiliary_goals"] = [{"goal_id": "duplicate", "description": "Use the established value",
                                    "dependencies": ["root:value"]}]
        bad = {"version": 1, "steps": [{"step_id": "S1", "title": "Add", "objective": "Compute 1+1",
                "obligation_ids": ["root:value"], "auxiliary_goal_ids": ["duplicate"], "method_id": "direct"}]}
        corrected = deepcopy(bad)
        corrected["steps"][0]["auxiliary_goal_ids"] = []
        self.open_faithful([spec, {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []},
            {"checkpoint": {**planner_checkpoint("FINAL"), "gaps": []}, "plan": bad},
            {"checkpoint": {**planner_checkpoint("FINAL"), "gaps": []}, "plan": corrected}], calls=4)
        self.terminal(self.submit())
        planners = [request for request in self.outbound if request["role"] == "planner"]
        self.assertEqual(2, len(planners))
        feedback = planners[1]["feedback"]
        self.assertEqual(bad, feedback["invalid_plan"])
        self.assertEqual([{"step_id": "S1", "objective_id": "duplicate", "prerequisite_id": "root:value",
                           "owner_step_id": "S1", "kind": "self_dependency"}], feedback.get("binding_errors"))

    def test_reasoner_empty_yield_is_repaired_before_serial_execution_continues(self):
        spec = deepcopy(SPEC)
        spec["root_obligations"].append({"obligation_id": "root:explain", "obligation_type": "universal",
            "statement": "Explain the addition", "prerequisite_ids": ["root:value"]})
        plan = {"version": 1, "steps": [
            {"step_id": "S1", "title": "Add", "objective": "Compute 1+1",
             "obligation_ids": ["root:value"], "auxiliary_goal_ids": [], "method_id": "direct"},
            {"step_id": "S2", "title": "Explain", "objective": "Explain the addition", "depends_on": ["S1"],
             "obligation_ids": ["root:explain"], "auxiliary_goal_ids": [], "method_id": "direct"},
        ]}
        first = reasoner_checkpoint("FINAL")
        first["checkpoint"].update(objective=plan["steps"][0]["objective"], argument="1+1=2")
        first["checkpoint"]["claims"][0]["statement"] = "1+1=2 by integer addition."
        bad = deepcopy(first)
        bad["checkpoint"]["status"] = "YIELD"
        second = deepcopy(first)
        second["checkpoint"].update(checkpoint_id="cp-2", objective=plan["steps"][1]["objective"])
        review = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": "",
                  "obligation_evidence": [{"obligation_id": "root:value",
                    "evidence_category": "universal_proof", "claim_indexes": [0]}]}
        second_review = deepcopy(review)
        second_review["obligation_evidence"][0]["obligation_id"] = "root:explain"
        stream_requests = [
            {"role": "planner", "checkpoint_protocol": True, "problem_spec": spec, "progress_policy": {"enabled": True}},
            *({"role": "step_verifier", "problem_spec": spec, "step": step} for step in plan["steps"]),
            *({"role": "reasoner", "checkpoint_protocol": True, "current_goal": step["objective"]}
              for step in plan["steps"]),
        ]
        self.open_faithful([spec, {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []},
            {"checkpoint": {**planner_checkpoint("FINAL"), "gaps": []}, "plan": plan},
            bad, first, review, second, second_review, {"final_response": "1+1=2"}, ACCEPT],
            calls=12, stream=True, stream_requests=stream_requests)
        final = self.terminal(self.submit())
        self.assertEqual("succeeded", final["status"])
        reasoners = [r for r in self.outbound if r["role"] == "reasoner"]
        self.assertEqual(3, len(reasoners))
        self.assertEqual(reasoners[0]["call_id"] + ":repair-1", reasoners[1]["call_id"])
        self.assertEqual(bad, json.loads(reasoners[1]["format_repair"]["previous_response"]))
        self.assertEqual(1, reasoners[0]["checkpoint_remaining_rounds"])
        self.assertEqual(2, len(final["result"]["solver"]["progress"]["steps"]))

    def test_reviewed_yield_lemma_survives_final_checkpoint_and_serial_advance(self):
        self.assert_reviewed_yield_serial()

    def test_tool_continuation_classification_binds_the_actual_final_review(self):
        self.assert_reviewed_yield_serial(verifier_tool=True)

    def test_new_conjecture_does_not_halt_serial_review_or_become_proof(self):
        self.assert_reviewed_yield_serial(conjecture=True)

    def assert_reviewed_yield_serial(self, *, verifier_tool=False, conjecture=False):
        spec = deepcopy(SPEC)
        spec["root_obligations"].append({"obligation_id": "root:check", "obligation_type": "universal",
            "statement": "Check the addition", "prerequisite_ids": ["root:value"]})
        plan = {"version": 1, "steps": [
            {"step_id": "S1", "title": "Add", "objective": "Compute 1+1",
             "obligation_ids": ["root:value"], "auxiliary_goal_ids": [], "method_id": "direct"},
            {"step_id": "S2", "title": "Check", "objective": "Check the addition", "depends_on": ["S1"],
             "obligation_ids": ["root:check"], "auxiliary_goal_ids": [], "method_id": "direct"},
        ]}
        partial = reasoner_checkpoint("YIELD", marker="partial")
        partial["checkpoint"]["objective"] = plan["steps"][0]["objective"]
        first = reasoner_checkpoint("FINAL", marker="complete")
        first["checkpoint"]["objective"] = plan["steps"][0]["objective"]
        second = reasoner_checkpoint("FINAL", marker="checked")
        second["checkpoint"]["objective"] = plan["steps"][1]["objective"]
        review = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": "",
                  "obligation_evidence": [{"obligation_id": "root:value",
                    "evidence_category": "universal_proof", "claim_indexes": [0]}]}
        partial_review = {**review, "classified_outcomes": [{
            "category": "Lemma", "statement": "partial", "scope": "integer addition",
            "claim_indexes": [0], "receipt_ids": [], "dependencies": []}]}
        if conjecture:
            partial_review["classified_outcomes"].append({
                "category": "Conjecture", "statement": "unproved extension", "scope": "unproved",
                "claim_indexes": [0], "receipt_ids": [], "dependencies": []})
        second_review = deepcopy(review)
        second_review["obligation_evidence"][0]["obligation_id"] = "root:check"
        registry = None
        partial_replies = [partial_review]
        if verifier_tool:
            from showcase.tools import ToolRegistry

            registry = ToolRegistry()
            registry.register("polynomial_check", lambda args: 2)

            def reviewed_with_receipt(request):
                reply = deepcopy(partial_review)
                reply["classified_outcomes"][0]["receipt_ids"] = [request["report"]["tool_receipts"][-1]["receipt_id"]]
                return reply

            partial_replies = [{**review, "verdict": "CHALLENGE", "goal_gate": "PARTIAL",
                "tool_request": {"tool": "polynomial_check", "arguments": {"coefficients": [1]},
                                 "scope": "finite_computation"}}, reviewed_with_receipt]
        stream_requests = [
            {"role": "planner", "checkpoint_protocol": True, "problem_spec": spec, "progress_policy": {"enabled": True}},
            *({"role": "step_verifier", "problem_spec": spec, "step": step} for step in plan["steps"]),
            *({"role": "reasoner", "checkpoint_protocol": True, "current_goal": step["objective"]}
              for step in plan["steps"]),
        ]
        self.open_faithful([spec, {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []},
            {"checkpoint": {**planner_checkpoint("FINAL"), "gaps": []}, "plan": plan},
            partial, *partial_replies, first, review, second, second_review, {"final_response": "1+1=2"}, ACCEPT],
            calls=14, stream=True, stream_requests=stream_requests, registry=registry)
        job_id = self.submit()
        final = self.terminal(job_id, timeout=30)
        self.assertEqual("succeeded", final["status"], final["result"]["solver"].get("result_reason"))
        with closing(sqlite3.connect(Path(self.data_dir) / "showcase.sqlite3")) as connection:
            state = json.loads(connection.execute(
                "SELECT state_json FROM solver_states WHERE run_id=?", (job_id,)).fetchone()[0])
        snapshot = state["proof_graph"]["snapshots"][-1]
        self.assertEqual(["conjecture_not_importable"] if conjecture else [],
                         [item["reason"] for item in snapshot["not_imported_records"]])
        self.assertTrue(any(row["status"] == "accepted" for row in snapshot["derivations"].values()))
        self.assertEqual(["ACCEPTED", "ACCEPTED"], [state["steps"][key]["status"] for key in ("S1", "S2")])
        if conjecture:
            self.assertNotIn("unproved extension", [item["statement"] for item in snapshot["propositions"].values()])
            return
        from showcase.solver_harness.proof_graph_sources import importable_ledger_rows

        ledger = state["verified_results_ledger"]
        review_id = ledger[0]["review_call_id"]
        if verifier_tool:
            self.assertTrue(review_id.endswith(":tool-1"))
            self.assertEqual(1, state["counters"]["tool_calls"])
        source_id = state["reasoner_checkpoints"][0]["call_id"]
        for path, value in [
            (("reasoner_checkpoints", 0, "argument"), "forged"),
            (("calls", source_id, "response", "checkpoint", "argument"), "forged"),
            (("calls", source_id, "plan_version"), 99),
            (("calls", review_id, "request", "report", "argument"), "forged"),
            (("calls", review_id, "status"), "unknown"),
            (("verified_results_ledger", 0, "invalidated"), True),
        ]:
            with self.subTest(tampered=path):
                altered = deepcopy(state)
                target = altered
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                imported, rejected = importable_ledger_rows(altered, altered["verified_results_ledger"])
                self.assertEqual([], imported)
                self.assertEqual(1, len(rejected))
