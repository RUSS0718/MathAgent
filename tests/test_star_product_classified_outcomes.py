"""Verifier-classified outcomes through the public STAR Job contract (ALIGN-AC-08/09).

The reviewer — never the Reasoner's report — decides what a review establishes.
Each classified outcome (Lemma, Conjecture, Computation, Definition, Answer) is
verified by the controller against the reviewed report, real tool receipts and
established dependencies before it is atomically appended to the authoritative
ledger; partial outcomes survive CHALLENGE, TRACE_BACK and PROPOSE_REPLAN while
Conjectures never become proven premises.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from showcase.final_evidence import artifact_identity
from showcase.run_budget import RunBudgetLimits
from showcase.tools import ToolRegistry
from tests.star_product_support import ACCEPT, StarJobFixture
from tests.test_star_product_challenge import META_ABORT
from tests.test_star_product_planning import FEATURES
from tests.test_star_product_tools import NEED_PLAN
from tests.star_recovery_worker import CLASSIFIED_LEMMA

PLAN = {"version": 1, "steps": [
    {"step_id": "s1", "title": "Base", "objective": "Establish the base fact"},
    {"step_id": "s2", "title": "Route", "objective": "Use the base fact",
     "depends_on": ["s1"]},
]}


def report(argument="", claims=None):
    return {"argument": argument, "claims": claims or [], "blocked": False}


LEMMA = "Forward direction holds for the boundary case"
CONJECTURE = "The full two-sided statement holds"
ANSWER = "The required sum equals 2"

# Classification issued while reviewing s2: s1 is already accepted, so the
# lemma may depend on it; both declarations anchor to s2's report claims.
CHALLENGE_CLASSIFIED = {
    "goal_gate": "PARTIAL", "logic_gate": "UNCERTAIN", "verdict": "CHALLENGE",
    "objection": "The reverse direction is not justified.",
    "classified_outcomes": [
        {"category": "Lemma", "statement": LEMMA,
         "scope": "boundary case of the route step", "claim_indexes": [0],
         "dependencies": ["s1"]},
        {"category": "Conjecture", "statement": CONJECTURE,
         "scope": "whole problem", "claim_indexes": [1]},
    ],
}

# Classification issued while reviewing a step that is not accepted yet: it
# cannot depend on anything beyond established results.
SELF_CHALLENGE_CLASSIFIED = {
    "goal_gate": "PARTIAL", "logic_gate": "UNCERTAIN", "verdict": "CHALLENGE",
    "objection": "The reverse direction is not justified.",
    "classified_outcomes": [
        {"category": "Lemma", "statement": LEMMA,
         "scope": "boundary case of this step", "claim_indexes": [0]},
        {"category": "Conjecture", "statement": CONJECTURE,
         "scope": "whole problem", "claim_indexes": [0]},
    ],
}

ACCEPT_VERDICT = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
                  "objection": ""}


def events_of(self, job_id):
    stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
    return [json.loads(line[6:]) for line in stream.splitlines()
            if line.startswith("data: ")]


class StarClassifiedOutcomesTest(StarJobFixture, unittest.TestCase):
    def run_public(self, replies, **config):
        self.open_star(replies, SHOWCASE_STAR_FEATURES=FEATURES,
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=20,
                                                            max_http_attempts=20),
                       **config)
        job_id = self.create_job()
        job = self.terminal(job_id)
        return job_id, job, events_of(self, job_id)

    def test_challenge_retains_proven_lemma_and_leaves_conjecture_unproven(self):
        """AC-08: the step does not advance, valid parts stay reusable, the
        conjecture never enters the proven premises of later roles."""
        replies = [
            NEED_PLAN, PLAN,
            report("Base fact established"),
            ACCEPT_VERDICT,
            report("Route attempt", claims=[
                {"statement": LEMMA, "label": "hard-verify"},
                {"statement": CONJECTURE, "label": "hard-verify"},
            ]),
            CHALLENGE_CLASSIFIED,
            report("Reverse direction completed", claims=[
                {"statement": CONJECTURE + " with both directions", "label": "hard-verify"},
            ]),
            {**ACCEPT_VERDICT, "classified_outcomes": [
                {"category": "Answer", "statement": ANSWER,
                 "scope": "whole problem", "dependencies": ["s1"]},
            ]},
            {"final_response": "2"},
            ACCEPT,
        ]
        job_id, job, events = self.run_public(replies)
        self.assertEqual("succeeded", job["status"], job)
        roles = [request["role"] for request in self.outbound]
        self.assertEqual(
            ["explore", "planner", "reasoner", "step_verifier", "reasoner",
             "step_verifier", "reasoner", "step_verifier", "final_generator",
             "whole_solution_verifier"], roles, self.outbound)
        # The step did not advance on CHALLENGE: the same step is re-dispatched.
        continued = self.outbound[6]
        self.assertEqual("reasoner", continued["role"])
        self.assertEqual("s2", continued["step"]["step_id"])
        # The continuation reasoner actually receives both classified outcomes.
        ledger = continued["role_context"]["state"]["verified_results_ledger"]
        self.assertEqual([LEMMA, CONJECTURE],
                         [item["statement"] for item in ledger], ledger)
        lemma, conjecture = ledger
        self.assertEqual("Lemma", lemma["category"])
        self.assertTrue(lemma["proven"])
        self.assertEqual(["s1"], lemma["dependencies"])
        self.assertTrue(lemma["result_id"])
        self.assertEqual("llm_reviewed", lemma["evidence_level"])
        self.assertEqual("s2", lemma["source"])
        self.assertTrue(lemma["review_call_id"].startswith(self.outbound[5]["call_id"]))
        self.assertEqual("Conjecture", conjecture["category"])
        self.assertFalse(conjecture["proven"])
        self.assertEqual("conjecture", conjecture["evidence_level"])
        # Proven facts flow on; the conjecture never becomes a proven premise.
        facts = self.outbound[8]["accepted_results"]
        self.assertIn(LEMMA, [fact["statement"] for fact in facts], facts)
        self.assertIn(ANSWER, [fact["statement"] for fact in facts])
        self.assertNotIn(CONJECTURE, [fact["statement"] for fact in facts])
        whole = self.outbound[9]["accepted_results"]
        self.assertNotIn(CONJECTURE, [fact["statement"] for fact in whole])
        self.assertIn(LEMMA, [fact["statement"] for fact in whole])
        # Public SSE and Evidence expose categories and the accounting outcome.
        reviewed = [event for event in events
                    if event.get("solver_event_type") == "step_reviewed"]
        self.assertEqual([None, {"Lemma": 1, "Conjecture": 1}, {"Answer": 1}],
                         [event.get("classified_outcomes") for event in reviewed], events)
        self.assertEqual([None, None, None],
                         [event.get("rejected_outcomes") for event in reviewed])
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        timeline = [item for item in evidence["timeline"]
                    if item.get("solver_event_type") == "step_reviewed"]
        self.assertEqual([None, {"Lemma": 1, "Conjecture": 1}, {"Answer": 1}],
                         [item.get("classified_outcomes") for item in timeline])
        entries = self.report(job_id)["solver"]["solver"]["progress"]["classified_results"]
        self.assertEqual({"Lemma", "Conjecture", "Answer"},
                         {item["category"] for item in entries}, entries)
        self.assertEqual([True, False, True],
                         [item["proven"] for item in entries])
        self.assertTrue(all(not item["invalidated"] for item in entries))
        digests = {item["statement_digest"] for item in entries}
        self.assertEqual(3, len(digests), entries)
        self.assertIn(artifact_identity(LEMMA)["sha256"], digests)
        self.assertIn(artifact_identity(CONJECTURE)["sha256"], digests)
        self.assertIn(artifact_identity(ANSWER)["sha256"], digests)

    def test_traceback_keeps_valid_outcomes_outside_the_archive(self):
        """AC-08: TRACE_BACK archives the failed step but a lemma established
        during an earlier challenge of a surviving step stays reusable."""
        replies = [
            NEED_PLAN, PLAN,
            report("Base attempt", claims=[{"statement": "s1 claim", "label": "hard-verify"}]),
            SELF_CHALLENGE_CLASSIFIED,
            report("Base completed"),
            ACCEPT_VERDICT,
            report("Route attempt"),
            {"goal_gate": "NO", "logic_gate": "FAIL", "verdict": "TRACE_BACK",
             "trace_back_to": 2, "objection": "The route is unsupported."},
            report("Route rebuilt"),
            ACCEPT_VERDICT,
            {"final_response": "2"},
            ACCEPT,
        ]
        job_id, job, events = self.run_public(replies)
        self.assertEqual("succeeded", job["status"], job)
        retry = self.outbound[8]
        self.assertEqual("reasoner", retry["role"])
        self.assertEqual("s2", retry["step"]["step_id"])
        ledger = retry["role_context"]["state"]["verified_results_ledger"]
        self.assertIn(LEMMA, [item["statement"] for item in ledger])
        self.assertTrue(all(not item["invalidated"] for item in ledger
                            if item["statement"] == LEMMA))
        self.assertIn("Base completed", [
            fact["statement"] for fact in retry["role_context"]["state"]["accepted_results"]])
        applied = next(event for event in events
                       if event.get("solver_event_type") == "trace_back_applied")
        self.assertEqual(0, applied["invalidated_result_count"])
        self.assertEqual(1, applied["rescued_result_count"])
        facts = self.outbound[10]["accepted_results"]
        self.assertIn(LEMMA, [fact["statement"] for fact in facts])

    def test_traceback_invalidates_outcomes_of_the_archived_step(self):
        """AC-09: outcomes sourced from an archived step die with it and are
        never revived for later roles."""
        replies = [
            NEED_PLAN,
            {"version": 1, "steps": [
                {"step_id": "only", "title": "Only", "objective": "Single step"}]},
            report("Only attempt", claims=[{"statement": "only claim", "label": "hard-verify"}]),
            SELF_CHALLENGE_CLASSIFIED,
            report("Only rebuilt"),
            {"goal_gate": "NO", "logic_gate": "FAIL", "verdict": "TRACE_BACK",
             "trace_back_to": 1, "objection": "The route is unsupported."},
            report("Only rebuilt again"),
            ACCEPT_VERDICT,
            {"final_response": "2"},
            ACCEPT,
        ]
        job_id, job, events = self.run_public(replies)
        self.assertEqual("succeeded", job["status"], job)
        applied = next(event for event in events
                       if event.get("solver_event_type") == "trace_back_applied")
        # Both classified outcomes of the archived step die with it.
        self.assertEqual(2, applied["invalidated_result_count"])
        retry = self.outbound[6]
        self.assertEqual("reasoner", retry["role"])
        ledger = retry["role_context"]["state"]["verified_results_ledger"]
        self.assertNotIn(LEMMA, [item["statement"] for item in ledger])
        facts = self.outbound[8]["accepted_results"]
        self.assertNotIn(LEMMA, [fact["statement"] for fact in facts])
        self.assertIn("Only rebuilt again", [fact["statement"] for fact in facts])

    def test_replan_ruling_controls_cross_plan_rescue_of_classified_outcomes(self):
        """AC-08: PROPOSE_REPLAN keeps classified outcomes; only the approved
        ruling's reusable_results carry them into the replacement plan."""
        def scenario(reusable_results):
            replies = [
                NEED_PLAN, PLAN,
                report("Base fact established"),
                ACCEPT_VERDICT,
                report("Route attempt", claims=[
                    {"statement": LEMMA, "label": "hard-verify"},
                    {"statement": CONJECTURE, "label": "hard-verify"},
                ]),
                CHALLENGE_CLASSIFIED,
                report("Route revised"),
                {"goal_gate": "NO", "logic_gate": "FAIL", "verdict": "PROPOSE_REPLAN",
                 "objection": "The route needs a different plan."},
                {**META_ABORT, "decision": "APPROVE_REPLAN",
                 "reason_summary": "Switch routes.",
                 "plan_summary": "Plan the direct route.",
                 "reusable_results": reusable_results},
                {"version": 2, "steps": [
                    {"step_id": "s3", "title": "Direct", "objective": "Direct route"}]},
                report("Direct fact"),
                ACCEPT_VERDICT,
                {"final_response": "2"},
                ACCEPT,
            ]
            return self.run_public(replies)

        job_id, job, _ = scenario(["Base fact established", LEMMA])
        self.assertEqual("succeeded", job["status"], job)
        planner = self.outbound[9]
        self.assertEqual("planner", planner["role"])
        self.assertIn(LEMMA, [fact["statement"] for fact in planner["accepted_results"]])
        self.assertNotIn(CONJECTURE,
                         [fact["statement"] for fact in planner["accepted_results"]])
        ledger = planner["role_context"]["state"]["verified_results_ledger"]
        self.assertNotIn(CONJECTURE, [item["statement"] for item in ledger])

        _, job, _ = scenario([])
        self.assertEqual("succeeded", job["status"], job)
        planner = self.outbound[9]
        self.assertNotIn(LEMMA, [fact["statement"] for fact in planner["accepted_results"]])

    def test_forged_receipts_and_unsupported_upgrades_are_rejected(self):
        """AC-09: forged references, nonexistent receipts, unsupported
        computations and invalid report sources never reach the ledger."""
        actual = []
        registry = ToolRegistry()
        registry.register("polynomial_check", lambda args: actual.append(args) or 2)

        def review(context):
            receipt = context["report"]["tool_receipts"][0]["receipt_id"]
            return {
                "goal_gate": "PARTIAL", "logic_gate": "UNCERTAIN", "verdict": "CHALLENGE",
                "objection": "One claim checks out; the rest does not.",
                "classified_outcomes": [
                    {"category": "Lemma", "statement": LEMMA,
                     "scope": "boundary case", "claim_indexes": [0]},
                    {"category": "Computation", "statement": "The registered check returned 2",
                     "scope": "finite_computation", "claim_indexes": [0],
                     "receipt_ids": [receipt]},
                    {"category": "Lemma", "statement": "Forged receipt lemma",
                     "scope": "boundary case", "claim_indexes": [0],
                     "receipt_ids": ["tool:forged"]},
                    {"category": "Lemma", "statement": "Unknown dependency lemma",
                     "scope": "boundary case", "claim_indexes": [0],
                     "dependencies": ["s-missing"]},
                    {"category": "Computation", "statement": "Unsupported computation",
                     "scope": "finite_computation", "claim_indexes": [0]},
                    {"category": "Lemma", "statement": "Invalid report source",
                     "scope": "boundary case", "claim_indexes": [9]},
                ],
            }

        replies = [
            NEED_PLAN,
            {"version": 1, "steps": [
                {"step_id": "only", "title": "Only", "objective": "Single step"}]},
            report("Check attempt", claims=[{
                "statement": "1+1=2", "label": "easy-verify",
                "tool_request": {"tool": "polynomial_check", "arguments": {"coefficients": [1]},
                                 "scope": "finite_computation", "expected_output": 2}}]),
            review,
            report("Only rebuilt"),
            ACCEPT_VERDICT,
            {"final_response": "2"},
            ACCEPT,
        ]
        self.open_star(replies,
                       SHOWCASE_STAR_FEATURES={**FEATURES, "local_code_tool": True},
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                           max_model_calls=16, max_http_attempts=16, max_tool_calls=2),
                       SHOWCASE_STAR_REGISTRY=registry)
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual(1, len(actual))
        reviewed = [event for event in events_of(self, job_id)
                    if event.get("solver_event_type") == "step_reviewed"]
        self.assertEqual({"Lemma": 1, "Computation": 1}, reviewed[0]["classified_outcomes"])
        self.assertEqual(4, reviewed[0]["rejected_outcomes"])
        continuation = self.outbound[4]
        self.assertEqual("reasoner", continuation["role"])
        ledger = continuation["role_context"]["state"]["verified_results_ledger"]
        self.assertEqual([LEMMA, "The registered check returned 2"],
                         [item["statement"] for item in ledger], ledger)
        computation = ledger[1]
        self.assertEqual("tool_verified", computation["evidence_level"])
        self.assertTrue(computation["proven"])
        self.assertEqual(1, len(computation["receipt_ids"]))
        for absent in ("tool:forged", "Forged receipt lemma", "Unknown dependency lemma",
                       "Unsupported computation", "Invalid report source"):
            self.assertNotIn(absent, json.dumps(ledger))


class StarClassifiedRecoveryTest(StarJobFixture, unittest.TestCase):
    def test_process_exit_after_classified_review_does_not_duplicate_outcomes(self):
        from showcase.flask_app import create_app
        from tests.star_recovery_worker import config, provider

        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            process = subprocess.run(
                [sys.executable, "-m", "tests.star_recovery_worker", directory, "classified"],
                capture_output=True, timeout=60)
            self.assertEqual(71, process.returncode, process.stderr.decode(errors="replace"))
            job_id = (folder / "job_id").read_text()
            with patch.dict(os.environ, {"INTERN_API_KEY": "scripted-only"}), patch(
                    "llm_client.requests.post", side_effect=lambda *a, **kw: provider(folder, kw)):
                app = create_app(config(folder))
                try:
                    self.app = app
                    self.client = app.test_client()
                    self.csrf = self.client.get("/api/check_auth").get_json()["csrf_token"]
                    response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={},
                                                headers=self.headers())
                    self.assertEqual(202, response.status_code, response.get_json())
                    job = self.terminal(job_id)
                    self.assertEqual("succeeded", job["status"], job)
                    entries = self.report(job_id)["solver"]["solver"]["progress"][
                        "classified_results"]
                finally:
                    for name in ("showcase_workspace_service", "showcase_run_service",
                                 "loopback_store"):
                        app.extensions[name].close()
            self.assertEqual(1, len(entries), entries)
            self.assertEqual("Lemma", entries[0]["category"])
            self.assertEqual(artifact_identity(CLASSIFIED_LEMMA)["sha256"],
                             entries[0]["statement_digest"])
            self.assertFalse(entries[0]["invalidated"])
            stored = [json.loads(line) for line
                      in (folder / "requests.jsonl").read_text().splitlines()]
            sightings = [
                item
                for request in stored
                if request.get("role") == "reasoner" and isinstance(request.get("role_context"), dict)
                for item in request["role_context"]["state"]["verified_results_ledger"]
                if item.get("category") == "Lemma"]
            self.assertEqual(1, len({item["result_id"] for item in sightings}), sightings)
            self.assertTrue(all(not item["invalidated"] for item in sightings))


@unittest.skipUnless(os.environ.get("MATHAGENT_TEST_PYTHON_IMAGE"),
                     "requires independently validated local Docker image ID")
class StarFullReferenceClassifiedOutcomeTest(StarJobFixture, unittest.TestCase):
    def test_reference_classified_computation_carries_real_isolated_receipt(self):
        """Full reference preset: a reviewer-classified Computation is backed by
        its own real isolated execution through the public artifact seam."""
        image = os.environ["MATHAGENT_TEST_PYTHON_IMAGE"]
        code = "import sympy as sp\nx=sp.symbols('x')\nprint(sp.factor(x**2-1))"
        expected = "(x - 1)*(x + 1)\n"

        def classified_review(context):
            receipt = context["report"]["tool_receipts"][0]["receipt_id"]
            return {
                "goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
                "objection": "The factorization was checked by isolated computation.",
                "classified_outcomes": [
                    {"category": "Computation",
                     "statement": "x^2-1 factors as (x-1)(x+1) in the checked environment",
                     "scope": "finite_computation", "claim_indexes": [],
                     "receipt_ids": [receipt]},
                    {"category": "Conjecture",
                     "statement": "The factorization pattern holds for every odd square",
                     "scope": "whole problem", "claim_indexes": []},
                ],
            }

        self.open_star(
            [NEED_PLAN,
             {"version": 1, "steps": [
                 {"step_id": "only", "title": "Only", "objective": "Factor x^2-1"}]},
             report("Factor attempt", claims=[
                 {"statement": "x^2-1 = (x-1)(x+1)", "label": "hard-verify"}]),
             {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": "",
              "tool_request": {"tool": "python_math", "arguments": {"code": code},
                               "scope": "finite_computation", "expected_output": expected}},
             classified_review,
             {"final_response": "x^2 - 1 = (x - 1)(x + 1)."},
             ACCEPT],
            SHOWCASE_STAR_FULL_ENABLED=True, SHOWCASE_STAR_PYTHON_IMAGE_ID=image)
        response = self.client.post("/api/agent/jobs", json={
            "message": "Factor x^2-1.", "session_id": self.session,
            "solver_mode": "star_reference"}, headers=self.headers())
        self.assertEqual(202, response.status_code, response.get_json())
        job_id = response.get_json()["job_id"]
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual("star_reference", job["result"]["execution_mode"])
        self.assertEqual([], job["result"]["missing_capabilities"])
        reviews = [context for context in self.outbound if context["role"] == "step_verifier"]
        self.assertEqual(2, len(reviews), [c["role"] for c in self.outbound])
        receipt = reviews[1]["report"]["tool_receipts"][0]
        self.assertEqual("step_verifier", receipt["source_role"])
        self.assertEqual("success", receipt["status"])
        self.assertTrue(receipt["executed"] and receipt["cleanup_verified"])
        self.assertEqual(image, receipt["image"])
        whole = next(request for request in self.outbound
                     if request["role"] == "whole_solution_verifier")
        facts = whole["accepted_results"]
        computation = next(fact for fact in facts
                           if fact["statement"] ==
                           "x^2-1 factors as (x-1)(x+1) in the checked environment")
        self.assertEqual("tool_verified", computation["evidence_level"])
        self.assertEqual([receipt["receipt_id"]], computation["receipt_ids"])
        self.assertNotIn("holds for every odd square", [fact["statement"] for fact in facts])
        resolved = self.client.get(
            f"/api/agent/jobs/{job_id}/artifacts/{receipt['stdout_ref']['sha256']}")
        self.assertEqual(200, resolved.status_code)
        self.assertEqual(expected.encode("utf-8"), resolved.data)
        entries = self.report(job_id)["solver"]["solver"]["progress"]["classified_results"]
        self.assertEqual({"Computation", "Conjecture"}, {item["category"] for item in entries})
        self.assertEqual([True, False], [item["proven"] for item in entries])
        digests = {item["statement_digest"] for item in entries}
        self.assertIn(artifact_identity(
            "x^2-1 factors as (x-1)(x+1) in the checked environment")["sha256"], digests)
        self.assertEqual(1, self.report(job_id)["budget"]["tool_calls"])


if __name__ == "__main__":
    unittest.main()
