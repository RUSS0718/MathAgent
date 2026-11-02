"""RB-03 public Job controls; only provider HTTP responses are scripted."""

import json
import unittest

from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import StarJobFixture

PROBLEM = "计算17×23并简要解释"
SOLUTION = "17×23=17×(20+3)=340+51=391，因此结果为391。"
NEED_PLAN = {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []}
PLAN = {"version": 1, "steps": [{"step_id": "calculate", "title": "计算并解释",
                                "objective": PROBLEM}]}
STEP = {"argument": SOLUTION, "claims": [{"statement": "17×23=391",
        "label": "easy-verify"}], "blocked": False}
DECLARATION = {"claim_index": 0, "both_directions_proved": False,
               "assumptions": [], "approach": "Distributive law"}
ACCEPT = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": ""}
WHOLE_ACCEPT = {"verdict": "ACCEPT", "reason": "The answer and requested explanation are complete."}
FEATURES = {"skills": True, "final_generation": True, "final_solution_review": True}
NOT_FOUND = {"verdict": "NOT_FOUND", "counterexample": "", "assumptions_checked": [],
             "violated_conclusion": "", "searched_scope": "Only the equality case x=0"}


class ProofObligationJobTest(StarJobFixture, unittest.TestCase):
    def run_job(self, replies, *, problem=PROBLEM, limit=10):
        """Exercise authenticated Job, SSE, report and Evidence on the same Run."""
        self.open_star(replies, SHOWCASE_STAR_FEATURES=FEATURES,
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                           max_model_calls=limit, max_http_attempts=limit))
        created = self.client.post("/api/agent/jobs", json={"message": problem,
            "session_id": self.session, "solver_mode": "star_limited"}, headers=self.headers())
        self.assertEqual(202, created.status_code, created.get_json())
        job_id = created.get_json()["job_id"]
        job = self.terminal(job_id)
        stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        events = [json.loads(line[6:]) for line in stream.splitlines() if line.startswith("data: ")]
        return job_id, job, events

    def test_numeric_answer_does_not_require_two_directions(self):
        declaration = {**DECLARATION, "claim_type": "numerical_evaluation"}
        job_id, job, events = self.run_job([
            NEED_PLAN, PLAN, STEP, {**ACCEPT, "answer_claim": declaration},
            {"final_response": SOLUTION}, WHOLE_ACCEPT,
        ], limit=6)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual(["explore", "planner", "reasoner", "step_verifier",
                          "final_generator", "whole_solution_verifier"],
                         [r["role"] for r in self.outbound])
        self.assertEqual(6, self.post.call_count)
        report = self.report(job_id)
        self.assertEqual(6, report["budget"]["logical_calls"])
        self.assertEqual(6, report["budget"]["http_attempts"])
        self.assertFalse(any(e.get("solver_event_type") == "counterexample_requested" for e in events))
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        self.assertIn(SOLUTION, json.dumps(evidence, ensure_ascii=False))

    def test_not_found_cannot_promote_missing_sharp_direction_to_lemma(self):
        statement = "The sharp lower bound for x² over real x is 0."
        step = {"argument": "x=0 attains 0; the lower bound is not proved.",
                "claims": [{"statement": statement, "label": "hard-verify"}], "blocked": False}
        # Legacy declaration: exercise the existing unsafe promotion, rather than
        # getting RED merely because the additive schema field is not supported.
        review = {**ACCEPT, "answer_claim": DECLARATION, "classified_outcomes": [
            {"category": "Lemma", "statement": statement, "scope": "all real x", "claim_indexes": [0]},
            {"category": "Conjecture", "statement": statement, "scope": "unproved lower bound",
             "claim_indexes": [0]},
        ]}
        problem = "Find and prove the sharp lower bound of x² over real x."
        plan = {"version": 1, "steps": [{"step_id": "bound", "title": "Bound and sharpness",
                                       "objective": problem}]}
        job_id, job, events = self.run_job([NEED_PLAN, plan, step, review, NOT_FOUND],
            problem=problem, limit=5)
        self.assertEqual("failed", job["status"])
        entries = self.report(job_id)["solver"]["solver"]["progress"]["classified_results"]
        self.assertFalse(any(item["proven"] for item in entries), entries)
        self.assertEqual(["Conjecture"], [item["category"] for item in entries])
        reviewed = next(e for e in events if e.get("solver_event_type") == "step_reviewed")
        self.assertEqual("CHALLENGE", reviewed["verdict"])
        self.assertEqual("UNCERTAIN", reviewed["logic_gate"])
        self.assertEqual(5, self.post.call_count)

    def test_complete_explore_preserves_explanation_in_three_real_requests(self):
        solved = {**NEED_PLAN, "assessment": "SOLVED", "solution_candidate": SOLUTION}
        job_id, job, events = self.run_job([
            solved, {"solution_candidate": SOLUTION}, WHOLE_ACCEPT,
        ], limit=3)
        self.assertEqual("succeeded", job["status"])
        self.assertEqual(SOLUTION, job["result"]["final_response"])
        self.assertEqual(["explore", "explore_polish", "whole_solution_verifier"],
                         [r["role"] for r in self.outbound])
        self.assertEqual(3, self.post.call_count)
        self.assertEqual(3, self.report(job_id)["budget"]["logical_calls"])
        self.assertEqual(3, self.report(job_id)["budget"]["http_attempts"])
        explore, polish, verifier = self.outbound
        self.assertEqual(explore["session_key"], polish["session_key"])
        self.assertNotEqual(polish["session_key"], verifier["session_key"])
        self.assertEqual([], verifier["session_history"])
        self.assertEqual(SOLUTION, polish["solution_candidate"])
        self.assertEqual(SOLUTION, verifier["solution_candidate"])
        self.assertTrue(any(e.get("solver_event_type") == "solution_review_assessed"
                            and e.get("verdict") == "ACCEPT" for e in events))
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        self.assertIn(SOLUTION, json.dumps(evidence, ensure_ascii=False))
        self.assertEqual("same_artifact", evidence["verification"]["binding"])
        whole = evidence["verification"]["history"][0]
        self.assertEqual("whole_solution_llm_review", whole["scope"])
        self.assertEqual(verifier["call_id"], whole["source"]["call_id"])
        self.assertEqual([SOLUTION, SOLUTION], [v["text"] for v in whole["versions"]])
        # External request assertions verify wiring, not a live model's obedience.
        for messages in self.outbound_messages[:2]:
            instructions = " ".join(m["content"] for m in messages if m["role"] == "system").lower()
            for requirement in ("brief explanation", "conditions", "domain", "answer format"):
                self.assertIn(requirement, instructions)

    def test_missing_explanation_is_rejected_then_legal_plan_completes(self):
        solved = {**NEED_PLAN, "assessment": "SOLVED", "solution_candidate": SOLUTION}
        job_id, job, events = self.run_job([
            solved, {"solution_candidate": "391"},
            {"verdict": "REJECT", "reason": "The required brief explanation is missing."},
            PLAN, STEP, ACCEPT, {"final_response": SOLUTION}, WHOLE_ACCEPT,
        ], limit=8)
        self.assertEqual("succeeded", job["status"])
        self.assertEqual(SOLUTION, job["result"]["final_response"])
        self.assertEqual("391", self.outbound[2]["solution_candidate"])
        self.assertEqual("planner", self.outbound[3]["role"])
        self.assertEqual(PROBLEM, self.outbound[3]["original_problem"])
        self.assertEqual("391", self.outbound[3]["exploration_findings"][0]["solution_candidate"])
        rejected = next(e for e in events if e.get("solver_event_type") == "solution_review_assessed")
        self.assertEqual("REJECT", rejected["verdict"])
        self.assertEqual("PLAN", rejected["next_phase"])
        self.assertEqual(8, self.report(job_id)["budget"]["logical_calls"])
        self.assertEqual(8, self.post.call_count)

    def test_claims_with_digits_still_require_applicable_directions(self):
        cases = [
            ("sharp_bound", "The sharp lower bound of x² is 0.", "Show x=0 attains 0"),
            ("extremum", "The minimum of x² is 0.", "Show x²≥0 but omit attainment"),
            ("necessary_and_sufficient", "x²=0 iff x=0.", "Prove only x=0 implies x²=0"),
        ]
        for claim_type, statement, approach in cases:
            with self.subTest(claim_type=claim_type):
                step = {"argument": approach, "claims": [
                    {"statement": statement, "label": "hard-verify"}], "blocked": False}
                review = {**ACCEPT, "answer_claim": {**DECLARATION,
                    "claim_type": claim_type, "approach": approach}}
                plan = {"version": 1, "steps": [{"step_id": "proof", "title": "Complete proof",
                                               "objective": statement}]}
                job_id, job, events = self.run_job([NEED_PLAN, plan, step, review, NOT_FOUND],
                    problem=statement + " Prove the complete claim.", limit=5)
                self.assertEqual("failed", job["status"])
                self.assertEqual(5, self.post.call_count)
                research = self.outbound[-1]
                self.assertEqual("counterexample_check", research["action"])
                self.assertEqual(statement, research["claim"])
                self.assertEqual([], research["allowed_tools"])
                reviewed = next(e for e in events if e.get("solver_event_type") == "step_reviewed")
                self.assertEqual("CHALLENGE", reviewed["verdict"])
                self.assertEqual("NOT_FOUND", reviewed["counterexample_verdict"])
                self.assertEqual("UNCERTAIN", reviewed["logic_gate"])
                self.assertEqual(5, self.report(job_id)["budget"]["logical_calls"])

    def test_complete_sharp_directions_can_finish_without_research(self):
        statement = "The sharp lower bound of x² over real x is 0."
        solution = "For real x, x²≥0; x=0 attains equality, so 0 is sharp."
        step = {"argument": solution, "claims": [
            {"statement": statement, "label": "hard-verify"}], "blocked": False}
        review = {**ACCEPT, "answer_claim": {**DECLARATION, "claim_type": "sharp_bound",
            "both_directions_proved": True, "approach": "Bound and equality case"}}
        plan = {"version": 1, "steps": [{"step_id": "proof", "title": "Bound and equality",
                                       "objective": statement}]}
        job_id, job, _ = self.run_job([NEED_PLAN, plan, step, review,
            {"final_response": solution}, WHOLE_ACCEPT], problem=statement, limit=6)
        self.assertEqual("succeeded", job["status"])
        self.assertNotIn("researcher", [r["role"] for r in self.outbound])
        self.assertEqual(6, self.report(job_id)["budget"]["logical_calls"])

    def test_contradictory_gates_with_missing_obligation_stop_without_rewriting(self):
        for goal, logic in (("NO", "PASS"), ("PARTIAL", "PASS"),
                            ("YES", "FAIL"), ("YES", "UNCERTAIN")):
            with self.subTest(goal=goal, logic=logic):
                review = {**ACCEPT, "goal_gate": goal, "logic_gate": logic,
                          "answer_claim": DECLARATION}
                job_id, job, events = self.run_job([NEED_PLAN, PLAN, STEP, review], limit=10)
                self.assertEqual("failed", job["status"])
                self.assertEqual(4, self.post.call_count)
                gate = next(e for e in events if e.get("solver_event_type") == "step_reviewed")
                self.assertFalse(gate["valid"])
                self.assertEqual(goal, gate["goal_gate"])
                self.assertEqual(logic, gate["logic_gate"])
                self.assertEqual(4, self.report(job_id)["budget"]["logical_calls"])

    def test_invalid_declaration_target_and_type_cannot_be_accepted(self):
        cases = [(dict(DECLARATION, claim_index=1), 4),
                 (dict(DECLARATION, claim_index=True), 5),
                 (dict(DECLARATION, claim_type="contains_digits"), 5),
                 (dict(DECLARATION, claim_type=None), 5),
                 (dict(DECLARATION, scope="another claim"), 5)]
        for declaration, calls in cases:
            with self.subTest(declaration=declaration):
                review = {**ACCEPT, "answer_claim": declaration}
                job_id, job, events = self.run_job([NEED_PLAN, PLAN, STEP, review, review])
                self.assertEqual("failed", job["status"])
                self.assertEqual(calls, self.post.call_count)
                self.assertNotIn("researcher", [r["role"] for r in self.outbound])
                gate = next(e for e in events if e.get("solver_event_type") == "step_reviewed")
                self.assertFalse(gate["valid"])
                self.assertEqual([], job["result"]["solver"]["recovery"]["unknown_calls"])
                self.assertEqual(calls, self.report(job_id)["budget"]["logical_calls"])

    def test_repeated_accept_with_missing_direction_terminates_at_challenge_cap(self):
        statement = "The sharp lower bound of x² over real x is 0."
        step = {"argument": "x=0 attains 0, but no bound proof is supplied.", "claims": [
            {"statement": statement, "label": "hard-verify"}], "blocked": False}
        plan = {"version": 1, "steps": [{"step_id": "bound", "title": "Bound and sharpness",
                                       "objective": statement}]}
        review = {**ACCEPT, "answer_claim": {**DECLARATION, "claim_type": "sharp_bound"}}
        replies = [NEED_PLAN, plan, step, review, NOT_FOUND]
        replies += [step, review, NOT_FOUND] * 3
        replies += [{"decision": "ABORT", "reason": "Missing proof after bounded challenges"}]
        job_id, job, events = self.run_job(replies, problem=statement, limit=20)
        self.assertEqual("failed", job["status"])
        self.assertEqual(15, self.post.call_count)
        self.assertEqual("meta", self.outbound[-1]["role"])
        self.assertEqual(4, sum(r.get("action") == "counterexample_check" for r in self.outbound))
        gates = [e for e in events if e.get("solver_event_type") == "step_reviewed"]
        self.assertEqual(["CHALLENGE"] * 4, [e["verdict"] for e in gates])
        self.assertEqual(15, self.report(job_id)["budget"]["logical_calls"])
        self.client.get(f"/api/agent/jobs/{job_id}")
        self.client.get(f"/api/runs/{job_id}/evidence")
        self.assertEqual(15, self.post.call_count)

    def test_incomplete_direction_preserves_separately_proved_partial_lemma(self):
        statement = "The sharp lower bound of x² over real x is 0."
        attained = "x=0 attains the value 0."
        step = {"argument": "Substituting 0 gives 0; the lower bound remains unproved.",
                "claims": [{"statement": statement, "label": "hard-verify"},
                           {"statement": attained, "label": "easy-verify"}], "blocked": False}
        plan = {"version": 1, "steps": [{"step_id": "bound", "title": "Bound and sharpness",
                                       "objective": statement}]}
        review = {**ACCEPT, "answer_claim": {**DECLARATION, "claim_type": "sharp_bound"},
                  "classified_outcomes": [
                      {"category": "Lemma", "statement": attained, "scope": "equality case",
                       "claim_indexes": [1]},
                      {"category": "Lemma", "statement": statement, "scope": "whole claim"},
                  ]}
        job_id, job, _ = self.run_job([NEED_PLAN, plan, step, review, NOT_FOUND],
            problem=statement, limit=5)
        self.assertEqual("failed", job["status"])
        entries = self.report(job_id)["solver"]["solver"]["progress"]["classified_results"]
        self.assertEqual(1, len(entries), entries)
        self.assertEqual("equality case", entries[0]["scope"])
        self.assertTrue(entries[0]["proven"])


if __name__ == "__main__":
    unittest.main()
