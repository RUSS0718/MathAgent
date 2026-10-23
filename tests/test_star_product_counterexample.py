"""Independent falsification is required before accepting an incomplete answer claim."""

import json
import unittest
import uuid
from unittest.mock import patch

import requests

from showcase.run_budget import RunBudgetLimits
from showcase.tools import ToolRegistry
from tests.star_product_support import StarJobFixture

NEED_PLAN = {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []}
PLAN = {"version": 1, "steps": [{"step_id": "private-optimum", "title": "Optimize",
    "objective": "Prove the minimum over all real x"}]}
STEP = {"argument": "At x=0 the value is zero, so zero is the minimum.",
    "claims": [{"statement": "The minimum of x over real x is 0.", "label": "hard-verify"}],
    "blocked": False}
TRIGGER = {"claim_index": 0, "both_directions_proved": False,
    "assumptions": ["x is real"], "approach": "Only test x=0"}
ACCEPT = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
    "objection": "", "answer_claim": TRIGGER}
FOUND = {"verdict": "FOUND_COUNTEREXAMPLE", "counterexample": "x=-1",
    "assumptions_checked": ["-1 is real"], "violated_conclusion": "-1 < 0",
    "searched_scope": "The single admissible value -1"}
NOT_FOUND = {"verdict": "NOT_FOUND", "counterexample": "", "assumptions_checked": [],
    "violated_conclusion": "", "searched_scope": "Only x=0 was searched"}
FEATURES = {"skills": True, "final_generation": True, "final_solution_review": True}
PROBLEM = "Find the minimum of x over all real numbers."


class StarCounterexampleTest(StarJobFixture, unittest.TestCase):
    def start(self, result=FOUND, *, limit=5, trigger=TRIGGER, tail=(), **config):
        self.open_star(
            [NEED_PLAN, PLAN, STEP, {**ACCEPT, "answer_claim": trigger}, result, *tail],
            SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=limit, max_http_attempts=limit),
            **config,
        )
        created = self.client.post("/api/agent/jobs", json={
            "message": PROBLEM, "session_id": self.session, "solver_mode": "star_limited",
        }, headers=self.headers())
        self.assertEqual(202, created.status_code)
        job_id = created.get_json()["job_id"]
        job = self.terminal(job_id)
        stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        events = [json.loads(line[6:]) for line in stream.splitlines() if line.startswith("data: ")]
        return job_id, job, events

    def assert_research_executed(self, job_id, job, events, verdict):
        self.assertEqual("failed", job["status"])
        self.assertEqual(["explore", "planner", "reasoner", "step_verifier", "researcher"],
                         [request["role"] for request in self.outbound])
        research = self.outbound[-1]
        self.assertEqual("counterexample_check", research["action"])
        self.assertEqual(PROBLEM, research["original_problem"])
        self.assertEqual(STEP["claims"][0]["statement"], research["claim"])
        self.assertEqual(TRIGGER["assumptions"], research["assumptions"])
        self.assertEqual(TRIGGER["approach"], research["forbidden_direction"])
        self.assertEqual([], research["allowed_tools"])
        self.assertEqual([], research["tool_policy"]["allow"])
        self.assertEqual([], research["session_history"])
        self.assertIn("construct-counterexamples", research["active_skill_ids"])
        self.assertNotEqual(self.outbound[-2]["session_key"], research["session_key"])
        completed = next(e for e in events if e.get("solver_event_type") == "counterexample_completed")
        self.assertEqual(verdict, completed["counterexample_verdict"])
        self.assertEqual("步骤 1", completed["step_id"])
        self.assertEqual("researcher", completed["role"])
        review = next(e for e in events if e.get("solver_event_type") == "step_reviewed")
        self.assertEqual("CHALLENGE", review["verdict"])
        budget = self.report(job_id)["budget"]
        self.assertEqual(5, budget["logical_calls"])
        self.assertEqual(5, budget["http_attempts"])
        self.assertEqual(0, budget["tool_calls"])
        self.assertEqual(50, budget["provider_known"]["total_tokens"])
        attempts = self.report(job_id)["request_attempts"]
        self.assertEqual(5, len({item["solver_call_id"] for item in attempts}))

    def test_found_counterexample_overrides_accept_and_is_charged_to_same_job(self):
        job_id, job, events = self.start()
        self.assert_research_executed(job_id, job, events, "FOUND_COUNTEREXAMPLE")
        review = next(e for e in events if e.get("solver_event_type") == "step_reviewed")
        self.assertEqual("FAIL", review["logic_gate"])
        self.assertIn("x=-1", review["objection_summary"])

    def test_not_found_is_bounded_search_and_does_not_complete_the_missing_proof(self):
        job_id, job, events = self.start(NOT_FOUND)
        self.assert_research_executed(job_id, job, events, "NOT_FOUND")
        review = next(e for e in events if e.get("solver_event_type") == "step_reviewed")
        self.assertEqual("PARTIAL", review["goal_gate"])
        self.assertEqual("UNCERTAIN", review["logic_gate"])
        self.assertIn("Conjecture", review["objection_summary"])
        self.assertFalse(any(e.get("verdict") == "ACCEPT" for e in events))
        before = len(self.outbound)
        for endpoint in (f"/api/agent/jobs/{job_id}", f"/api/agent/jobs/{job_id}/report",
                         f"/api/runs/{job_id}/evidence", f"/api/agent/jobs/{job_id}/events"):
            self.assertEqual(200, self.client.get(endpoint).status_code)
        self.assertEqual(before, len(self.outbound))

    def test_budget_exhaustion_prevents_research_and_never_accepts_missing_proof(self):
        job_id, job, events = self.start(limit=4)
        self.assertEqual("failed", job["status"])
        self.assertEqual(4, len(self.outbound))
        self.assertEqual(4, self.report(job_id)["budget"]["logical_calls"])
        self.assertEqual("partial_budget_exhausted", job["result"]["solver"]["status"])
        self.assertFalse(any(e.get("verdict") == "ACCEPT" for e in events))
        self.assertFalse(any(e.get("solver_event_type") == "counterexample_completed" for e in events))

    def test_invalid_claim_target_cannot_schedule_unbound_research_or_accept(self):
        _, job, events = self.start(trigger={**TRIGGER, "claim_index": 1})
        self.assertEqual("failed", job["status"])
        self.assertEqual(4, len(self.outbound))
        review = next(e for e in events if e.get("solver_event_type") == "step_reviewed")
        self.assertFalse(review["valid"])
        self.assertEqual("STEP_VERIFY", review["solver"]["phase"])

    def test_research_tool_or_cross_run_instruction_is_rejected_without_registry_dispatch(self):
        executed = []
        registry = ToolRegistry()
        registry.register("polynomial_check", lambda args: executed.append(args))
        for extra in (
            {"tool_request": {"tool": "polynomial_check", "arguments": {"code": "print(1)"}}},
            {"target_run_id": "another-run"},
        ):
            with self.subTest(extra=extra):
                job_id, job, events = self.start({**FOUND, **extra}, SHOWCASE_STAR_REGISTRY=registry)
                self.assertEqual("failed", job["status"])
                self.assertEqual(5, len(self.outbound))
                self.assertEqual([], executed)
                self.assertEqual(0, self.report(job_id)["budget"]["tool_calls"])
                review = next(e for e in events if e.get("solver_event_type") == "step_reviewed")
                self.assertFalse(review["valid"])
                completed = next(e for e in events if e.get("solver_event_type") == "counterexample_completed")
                self.assertEqual("INVALID", completed["counterexample_verdict"])

    def test_skipped_dispatch_is_rejected_and_public_acceptance_detects_the_bypass(self):
        with patch("showcase.solver_harness.counterexample.run_check",
                   side_effect=lambda _harness, run, **_kwargs: run):
            job_id, job, events = self.start()
        self.assertEqual("failed", job["status"])
        review = next(e for e in events if e.get("solver_event_type") == "step_reviewed")
        self.assertFalse(review["valid"])
        self.assertEqual(4, len(self.outbound))
        with self.assertRaises(AssertionError):
            self.assert_research_executed(job_id, job, events, "FOUND_COUNTEREXAMPLE")

    def test_repaired_proof_can_finish_without_promoting_the_original_conjecture(self):
        repaired = {"argument": "For every real x, x-1 is real and smaller; there is no minimum.",
            "claims": [{"statement": "There is no minimum over the real numbers.",
                        "label": "hard-verify"}], "blocked": False}
        reviewed = {**ACCEPT, "answer_claim": {**TRIGGER, "both_directions_proved": True,
                    "approach": "Show every real candidate has a smaller admissible value"}}
        job_id, job, events = self.start(NOT_FOUND, limit=9, tail=[
            repaired, reviewed, {"final_response": "There is no minimum."},
            {"verdict": "ACCEPT", "reason": "The proof covers every real candidate."},
        ])
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual(1, sum(item["role"] == "researcher" for item in self.outbound))
        generator = next(item for item in self.outbound if item["role"] == "final_generator")
        self.assertEqual(["There is no minimum over the real numbers."],
                         [item["statement"] for item in generator["accepted_results"]])
        revisions = [item for item in events if item.get("solver_event_type") == "step_reviewed"]
        self.assertEqual(["CHALLENGE", "ACCEPT"], [item["verdict"] for item in revisions])
        self.assertEqual(9, self.report(job_id)["budget"]["logical_calls"])

    def test_unknown_research_preserves_consumption_and_does_not_retry_on_reads(self):
        job_id, job, events = self.start(requests.Timeout())
        self.assertEqual("failed", job["status"])
        self.assertEqual(5, len(self.outbound))
        budget = self.report(job_id)["budget"]
        self.assertEqual(5, budget["logical_calls"])
        self.assertEqual(1, budget["unresolved_attempts"])
        self.assertFalse(any(e.get("verdict") == "ACCEPT" for e in events))
        self.assertFalse(any(e.get("solver_event_type") == "counterexample_completed" for e in events))
        self.client.get(f"/api/agent/jobs/{job_id}")
        self.client.get(f"/api/agent/jobs/{job_id}/report")
        self.assertEqual(5, len(self.outbound))

    def test_unknown_research_retries_only_with_explicit_new_identity_and_reuses_verifier(self):
        job_id, first, _ = self.start(requests.Timeout(), limit=10)
        old = first["result"]["solver"]["recovery"]["unknown_calls"][0]["call_id"]
        deadline = first["result"]["budget"]["deadline_at"]
        rejected = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={},
                                    headers=self.headers())
        self.assertEqual(409, rejected.status_code)
        repaired = {"argument": "Every real x has a smaller real value x-1.",
            "claims": [{"statement": "There is no minimum.", "label": "hard-verify"}],
            "blocked": False}
        self.replies.extend([
            NOT_FOUND, repaired,
            {**ACCEPT, "answer_claim": {**TRIGGER, "both_directions_proved": True}},
            {"final_response": "There is no minimum."}, {"verdict": "ACCEPT"},
        ])
        response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={
            "retry_call": {"call_id": old, "new_call_id": str(uuid.uuid4())},
        }, headers=self.headers())
        self.assertEqual(202, response.status_code, response.get_json())
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"], final)
        self.assertEqual(2, sum(item["role"] == "researcher" for item in self.outbound))
        self.assertEqual(2, sum(item["role"] == "step_verifier" for item in self.outbound))
        self.assertEqual(deadline, final["result"]["budget"]["deadline_at"])
        self.assertEqual(10, final["result"]["budget"]["http_attempts"])
        retries = final["result"]["solver"]["recovery"]["retries"]
        self.assertEqual(old, retries[0]["retry_of"])


if __name__ == "__main__":
    unittest.main()
