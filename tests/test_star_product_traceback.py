"""Trace-back and replan through one public Job and real STAR dispatch."""

import json
import unittest

from showcase.final_evidence import artifact_identity
from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import ACCEPT, StarJobFixture
from tests.test_star_product_challenge import META_ABORT
from tests.test_star_product_planning import FEATURES
from tests.test_star_product_tools import NEED_PLAN, VERDICT

PLAN = {"version": 1, "steps": [
    {"step_id": "independent", "title": "Known", "objective": "Establish safe fact"},
    {"step_id": "wrong", "title": "Route", "objective": "Try old route"},
    {"step_id": "dependent", "title": "Use", "objective": "Use old route", "depends_on": ["wrong"]},
    {"step_id": "finish", "title": "Finish", "objective": "Complete", "depends_on": ["dependent"]},
]}
TRACE = {"goal_gate": "NO", "logic_gate": "FAIL", "verdict": "TRACE_BACK",
         "trace_back_to": 2, "objection": "Unsupported route"}
PROPOSE = {"goal_gate": "NO", "logic_gate": "FAIL", "verdict": "PROPOSE_REPLAN",
           "objection": "Use a different route"}


def report(argument, **extra):
    return {"argument": argument, "claims": [], "blocked": False, **extra}


class StarTracebackTest(StarJobFixture, unittest.TestCase):
    def run_public(self, replies):
        self.open_star(replies, SHOWCASE_STAR_FEATURES=FEATURES,
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=28, max_http_attempts=28))
        job_id = self.create_job()
        job = self.terminal(job_id)
        stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        events = [json.loads(line[6:]) for line in stream.splitlines() if line.startswith("data: ")]
        return job_id, job, events

    def test_traceback_archives_dependents_and_rescues_only_independent_facts(self):
        job_id, job, events = self.run_public([
            {**NEED_PLAN, "candidates": ["candidate is not a fact"]}, PLAN, report("safe reviewed fact"), VERDICT,
            report("old wrong fact"), VERDICT, report("old dependent fact"), VERDICT,
            report("private rejected proof"), TRACE,
            report("new route"), VERDICT, report("new dependent"), VERDICT,
            report("new completion"), VERDICT, {"final_response": "2"}, ACCEPT,
        ])
        self.assertEqual("succeeded", job["status"], job)
        reasoners = [r for r in self.outbound if r["role"] == "reasoner"]
        reset = reasoners[4]
        self.assertEqual("wrong", reset["step"]["step_id"])
        self.assertNotEqual(reasoners[1]["session_key"], reset["session_key"])
        self.assertNotEqual(reasoners[1]["call_id"], reset["call_id"])
        state = reset["role_context"]["state"]
        self.assertEqual(["safe reviewed fact"], [r["statement"] for r in state["accepted_results"]])
        self.assertEqual(["safe reviewed fact"], [r["statement"] for r in reset["rescued_results"]])
        failure = reset["failure_records"][0]
        self.assertEqual({"wrong", "dependent", "finish"}, set(failure["archived_steps"]))
        self.assertEqual(["old wrong fact", "old dependent fact"],
                         [r["statement"] for r in failure["invalidated_results"]])
        event = next(e for e in events if e.get("solver_event_type") == "trace_back_applied")
        self.assertEqual((2, 4, 3, 2, 1), tuple(event.get(k) for k in (
            "trace_back_to", "from_step_index", "archived_step_count", "invalidated_result_count", "rescued_result_count")))
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        self.assertTrue(any(e.get("solver_event_type") == "trace_back_applied" for e in evidence["timeline"]))
        self.assertEqual("fault_injection", evidence["solver"]["evidence_kind"])
        self.assertEqual(job_id, self.report(job_id)["solver"]["solver"]["run_id"])
        binding = self.report(job_id)["checks"]["history"][-1]
        self.assertEqual(1, binding["source"]["plan_version"])
        self.assertEqual(1, binding["source"]["attempt_index"])
        self.assertEqual({artifact_identity(text)["sha256"] for text in
            ("safe reviewed fact", "new route", "new dependent", "new completion")},
            {fact["statement_artifact"]["sha256"] for fact in binding["fact_sources"]})
        final_request = next(r for r in self.outbound if r["role"] == "whole_solution_verifier")
        statements = [fact["statement"] for fact in final_request["accepted_results"]]
        self.assertIn("safe reviewed fact", statements)
        self.assertNotIn("old wrong fact", statements)
        self.assertNotIn("old dependent fact", statements)
        for hidden in ("private rejected proof", "old wrong fact", "candidate is not a fact"):
            self.assertNotIn(hidden, json.dumps(events))

    def test_meta_replan_preserves_history_and_executes_new_objective_with_safe_reuse(self):
        decision = {**META_ABORT, "decision": "APPROVE_REPLAN", "reason_summary": "Old route failed",
                    "forbidden_directions": ["do not repeat old route"],
                    "reusable_results": ["safe reviewed fact", "old wrong fact", "invented theorem"]}
        new_plan = {"version": 2, "steps": [
            {"step_id": "fresh", "title": "Fresh", "objective": "Use independent bound"}]}
        job_id, job, events = self.run_public([
            NEED_PLAN, PLAN, report("safe reviewed fact"), VERDICT,
            report("old wrong fact"), VERDICT, report("old dependent fact"), VERDICT,
            report("private rejected proof"), TRACE,
            report("private failed argument"), PROPOSE, decision, new_plan,
            report("fresh proof"), VERDICT, {"final_response": "2"}, ACCEPT,
        ])
        self.assertEqual("succeeded", job["status"], job)
        planner = [r for r in self.outbound if r["role"] == "planner"][1]
        self.assertEqual(2, planner["plan_version"])
        self.assertEqual(["do not repeat old route"], planner["forbidden_directions"])
        self.assertEqual(["safe reviewed fact"], [r["statement"] for r in planner["accepted_results"]])
        self.assertEqual(2, len(planner["failure_records"]))
        self.assertEqual(PLAN, planner["failure_records"][-1]["archived_plan"])
        self.assertEqual("private failed argument", planner["failure_records"][-1]["archived_steps"]["wrong"]["report"]["argument"])
        fresh = [r for r in self.outbound if r["role"] == "reasoner"][-1]
        self.assertEqual("Use independent bound", fresh["step"]["objective"])
        self.assertEqual(["safe reviewed fact"], [r["statement"] for r in fresh["rescued_results"]])
        self.assertEqual(2, fresh["role_context"]["state"]["plan_version"])
        archived = next(e for e in events if e.get("solver_event_type") == "plan_archived")
        self.assertEqual(1, archived.get("archived_plan_version"))
        self.assertEqual(2, archived.get("plan_version"))
        self.assertTrue(any(e.get("solver_event_type") == "plan_replaced" for e in events))
        self.assertEqual(job_id, self.report(job_id)["solver"]["solver"]["run_id"])
        binding = self.report(job_id)["checks"]["history"][-1]
        self.assertEqual(2, binding["source"]["plan_version"])
        self.assertEqual(2, binding["source"]["attempt_index"])
        self.assertEqual({artifact_identity(text)["sha256"] for text in
            ("safe reviewed fact", "fresh proof")},
            {fact["statement_artifact"]["sha256"] for fact in binding["fact_sources"]})
        rescued = next(f for f in binding["fact_sources"] if f["rescued"])
        self.assertTrue(rescued["rescued"])
        self.assertEqual(artifact_identity("safe reviewed fact"), rescued["statement_artifact"])
        final_request = next(r for r in self.outbound if r["role"] == "whole_solution_verifier")
        self.assertEqual(["safe reviewed fact", "fresh proof"],
                         [fact["statement"] for fact in final_request["accepted_results"]])
        self.assertNotIn("private failed argument", json.dumps(events))

    def test_illegal_verifier_targets_never_guess_or_restart_a_step(self):
        for target in (None, True, 5):
            with self.subTest(target=target):
                _, job, events = self.run_public([
                    NEED_PLAN, PLAN, report("private unresolved proof"),
                    {**TRACE, "trace_back_to": target},
                ])
                self.assertEqual("failed", job["status"])
                self.assertEqual(1, sum(r["role"] == "reasoner" for r in self.outbound))
                self.assertFalse(any(e.get("solver_event_type") == "trace_back_applied" for e in events))
                self.assertFalse(any(e.get("verdict") == "ACCEPT" for e in events))
                self.assertNotIn("private unresolved proof", json.dumps(events))


if __name__ == "__main__":
    unittest.main()
