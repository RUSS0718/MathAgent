"""Illegal plans and contradictory acceptance cannot advance a public Job."""

import json
import unittest

from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import ACCEPT, RawProviderContent, StarJobFixture
from tests.test_star_product_planning import FEATURES, STEP
from tests.test_star_product_tools import NEED_PLAN, PLAN, VERDICT

TWO_STEPS = {"version": 1, "steps": [*PLAN["steps"], {
    "step_id": "conclude", "title": "Conclude", "objective": "State the sum", "depends_on": ["sum"],
}]}


class StarGateTest(StarJobFixture, unittest.TestCase):
    def start(self, replies, *, limit=16):
        self.open_star(replies, SHOWCASE_STAR_FEATURES=FEATURES,
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=limit, max_http_attempts=limit))
        job_id = self.create_job()
        job = self.terminal(job_id)
        stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        events = [json.loads(line[6:]) for line in stream.splitlines() if line.startswith("data: ")]
        return job_id, job, events

    def test_contradictory_accept_does_not_execute_next_step(self):
        for goal, logic in (("NO", "PASS"), ("PARTIAL", "PASS"), ("YES", "FAIL"), ("YES", "UNCERTAIN")):
            with self.subTest(goal=goal, logic=logic):
                job_id, job, events = self.start([
                    NEED_PLAN, TWO_STEPS, STEP, {**VERDICT, "goal_gate": goal, "logic_gate": logic},
                ])
                self.assertEqual("failed", job["status"])
                self.assertEqual(4, len(self.outbound))
                self.assertEqual("partial_aborted", job["result"]["solver"]["status"])
                self.assertEqual("STEP_VERIFY", job["result"]["solver"]["phase"])
                run = self.client.get(f"/api/runs/{job_id}").get_json()
                self.assertEqual("partial_aborted", run["result"]["solver"]["status"])
                gate = next(e for e in events if e.get("solver_event_type") == "step_reviewed")
                self.assertFalse(gate["valid"])
                self.assertEqual("步骤 1", gate["step_id"])
                self.assertEqual("STEP_VERIFY", gate["solver"]["phase"])

    def test_malformed_verifier_reply_is_persisted_as_needs_review(self):
        job_id, job, events = self.start([
            NEED_PLAN, TWO_STEPS, STEP, {"unexpected": "shape"},
        ])
        self.assertEqual("failed", job["status"])
        self.assertEqual(4, len(self.outbound))
        self.assertEqual("partial_aborted", job["result"]["solver"]["status"])
        self.assertEqual("STEP_VERIFY", job["result"]["solver"]["phase"])
        run = self.client.get(f"/api/runs/{job_id}").get_json()
        self.assertEqual("partial_aborted", run["result"]["solver"]["status"])
        self.assertEqual(["explore", "planner", "reasoner", "step_verifier"],
                         [request["role"] for request in self.outbound])
        gate = next(e for e in events if e.get("solver_event_type") == "step_reviewed")
        self.assertFalse(gate["valid"])
        self.assertEqual("STEP_VERIFY", gate["solver"]["phase"])

    def test_valid_gates_accept_once_and_pass_only_accepted_dependencies(self):
        job_id, job, events = self.start([
            NEED_PLAN, TWO_STEPS, STEP, VERDICT, STEP, VERDICT,
            {"final_response": "2"}, ACCEPT,
        ])
        self.assertEqual("succeeded", job["status"], job)
        reasoners = [r for r in self.outbound if r["role"] == "reasoner"]
        self.assertEqual(["sum", "conclude"], [r["step"]["step_id"] for r in reasoners])
        facts = reasoners[1]["role_context"]["state"]["accepted_results"]
        self.assertEqual(["sum"], [fact["source"] for fact in facts])
        self.assertEqual("llm_reviewed", facts[0]["evidence_level"])
        accepted = [e for e in events if e.get("solver_event_type") == "step_reviewed" and e.get("valid")]
        self.assertEqual(["步骤 1", "步骤 2"], [e["step_id"] for e in accepted])
        self.assertEqual(len(events), len({e.get("solver_event_id", e.get("type")) for e in events}))
        before = len(self.outbound)
        self.client.get(f"/api/runs/{job_id}/evidence")
        self.client.get(f"/api/agent/jobs/{job_id}/events")
        self.assertEqual(before, len(self.outbound))

    def test_repeated_invalid_plans_never_execute_reasoner(self):
        invalid_plans = [
            {"not_a_plan": True},
            {"version": 1, "steps": [*PLAN["steps"], *PLAN["steps"]]},
            {"version": 1, "steps": [{**PLAN["steps"][0], "depends_on": ["future"]}]},
            {"version": 1, "steps": [{**PLAN["steps"][0], "step_id": str(i)} for i in range(21)]},
            {"version": 1, "steps": [{**PLAN["steps"][0], "objective": " "}]},
        ]
        for plan in invalid_plans:
            with self.subTest(plan=plan):
                _, job, _ = self.start([NEED_PLAN, plan, plan])
                self.assertEqual("failed", job["status"])
                self.assertEqual(["explore", "planner", "planner"], [r["role"] for r in self.outbound])
                self.assertEqual("unknown", job["result"]["verification"]["status"])

    def test_malformed_plan_replies_get_one_repair_then_fail_closed(self):
        _, job, _ = self.start([
            NEED_PLAN, RawProviderContent("{"), RawProviderContent("not-json"),
        ])
        self.assertEqual("failed", job["status"])
        planners = [r for r in self.outbound if r["role"] == "planner"]
        self.assertEqual(2, len(planners))
        self.assertEqual(1, planners[1]["repair_attempt"])
        self.assertIsNone(planners[1]["invalid_plan"])
        self.assertIn("mapping", planners[1]["validation_error"])
        self.assertEqual(["explore", "planner", "planner"], [r["role"] for r in self.outbound])

    def test_budget_stop_never_dispatches_unreviewable_next_step(self):
        _, job, _ = self.start([NEED_PLAN, TWO_STEPS, STEP, VERDICT], limit=4)
        self.assertEqual("failed", job["status"])
        self.assertEqual(4, len(self.outbound))
        self.assertEqual(4, job["result"]["budget"]["logical_calls"])
        self.assertNotEqual("completed_llm_reviewed", job["result"]["solver"]["status"])

    def test_fabricated_verified_claim_cannot_become_tool_evidence(self):
        step = {**STEP, "claims": [{"statement": "2 is the sum", "label": "verified",
                                    "tool_evidence_refs": ["fabricated-receipt"]},
                                   {"statement": "1+1=2", "label": "easy-verify"}]}
        _, job, _ = self.start([NEED_PLAN, PLAN, step, VERDICT, {"final_response": "2"}, ACCEPT])
        self.assertEqual("succeeded", job["status"], job)
        report = next(r for r in self.outbound if r["role"] == "step_verifier")["report"]
        self.assertEqual(["hard-verify", "easy-verify"], [c["label"] for c in report["claims"]])
        self.assertTrue(all(c["tool_evidence_refs"] == [] for c in report["claims"]))
        self.assertEqual("unknown", job["result"]["verification"]["status"])


if __name__ == "__main__":
    unittest.main()
