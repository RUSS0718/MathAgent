"""Guidance replan enters an independent ReplanDecision (ALIGN-AC-02, ALIGN-AC-14).

The scripted provider answers by outbound context, so the same public Job scenario
runs against the current build and against a deliberate bypass of the approval gate:
a Guidance request never archives a plan by itself, only this transition's valid
unconsumed APPROVE_REPLAN ruling does.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from showcase.run_budget import RunBudgetLimits
from showcase.tools import ToolRegistry
from tests.star_product_support import ACCEPT, StarJobFixture
from tests.star_recovery_worker import config as worker_config, provider as worker_provider
from tests.test_star_product_tools import FEATURES, NEED_PLAN

GUIDANCE_REPLAN = {
    "action_type": "replan", "specific_task": "REPLAN_TASK_SENTINEL",
    "use_pure_reasoning": False, "trace_back_to": None,
    "rationale": "Use a bounded local recovery",
}
RULING_FIRST = {
    "decision": "APPROVE_REPLAN", "reason_summary": "first route archived",
    "plan_summary": "Switch to the direct construction",
    "forbidden_directions": ["OLD_DIRECTION"], "reusable_results": ["A1_FACT"],
    "trace_back_to": None,
}
RULING_SECOND = {
    "decision": "APPROVE_REPLAN", "reason_summary": "second route archived",
    "plan_summary": "Switch to the symmetric argument",
    "forbidden_directions": ["NEW_DIRECTION"], "reusable_results": ["B1_FACT"],
    "trace_back_to": None,
}
RULING_CONTINUE = {
    "decision": "CONTINUE", "reason_summary": "One more attempt on the same route",
    "plan_summary": "", "forbidden_directions": [], "reusable_results": [],
    "trace_back_to": None,
}
RULING_ABORT = {
    "decision": "ABORT", "reason_summary": "The requested route cannot be repaired",
    "plan_summary": "", "forbidden_directions": [], "reusable_results": [],
    "trace_back_to": None,
}
PLANS = {
    1: {"version": 1, "steps": [
        {"step_id": "a1", "title": "Base", "objective": "establish the base fact"},
        {"step_id": "a2", "title": "Extend", "objective": "extend the fact",
         "depends_on": ["a1"]},
    ]},
    2: {"version": 2, "steps": [
        {"step_id": "b1", "title": "Direct", "objective": "direct construction"},
        {"step_id": "b2", "title": "Conclude", "objective": "conclude the route",
         "depends_on": ["b1"]},
    ]},
    3: {"version": 3, "steps": [
        {"step_id": "c1", "title": "Symmetric", "objective": "symmetric argument"},
    ]},
}


def report(argument, *, blocked=False):
    return {"argument": argument, "claims": [], "blocked": blocked}


def star_replier(rulings, blocked):
    """Answer every outbound request by role; ``blocked`` holds (step_id, attempt).

    Step b2 proposes a replan on its first review only, so a CONTINUE ruling can
    actually finish the plan instead of looping on the same objection.
    """
    reviews = {}

    def replier(context):
        role = context["role"]
        if role == "explore":
            return NEED_PLAN
        if role == "planner":
            return PLANS[context["plan_version"]]
        if role == "meta":
            if context.get("action") == "delegate_research_task":
                return {"tasks": []}
            if context.get("guidance_request") is not None:
                return GUIDANCE_REPLAN
            return rulings[context["plan_version"]]
        if role == "reasoner":
            step_id = context["step"]["step_id"]
            # The attempt rides in the session key in both presets; the full
            # reference request carries no nested role_context.
            match = re.search(r"-attempt-(\d+)$", context.get("session_key", ""))
            attempt = int(match.group(1)) if match else 0
            if (step_id, attempt) in blocked:
                return report(f"{step_id} attempt blocked", blocked=True)
            return report(f"{step_id.upper()}_FACT")
        if role == "step_verifier":
            step_id = context["step"]["step_id"]
            seen = reviews.get(step_id, 0)
            reviews[step_id] = seen + 1
            if step_id == "b2" and seen == 0:
                return {"goal_gate": "NO", "logic_gate": "FAIL",
                        "verdict": "PROPOSE_REPLAN", "objection": "The route dead-ends"}
            return {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
                    "objection": ""}
        if role == "final_generator":
            return {"final_response": "2"}
        return {"verdict": "ACCEPT", "reason": "Addition"}
    return replier


class StarReplanDecisionTest(StarJobFixture, unittest.TestCase):
    IMAGE = os.environ.get("MATHAGENT_TEST_PYTHON_IMAGE")

    def terminal(self, job_id):
        # The independent ReplanDecision adds a meta round trip to scripted Jobs;
        # poll longer than the shared 8s window before calling the run stalled.
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            job = self.job(job_id)
            if job["status"] in {"succeeded", "failed", "canceled"}:
                return job
            time.sleep(0.05)
        self.fail("public STAR observation timed out")

    def run_public(self, replier, *, full=False):
        registry = ToolRegistry()
        registry.register("polynomial_check", lambda _args: None)
        config = {
            "SHOWCASE_STAR_FEATURES": {**FEATURES, "meta_guidance": True},
            "SHOWCASE_STAR_BUDGET": RunBudgetLimits(max_model_calls=28, max_http_attempts=28),
            "SHOWCASE_STAR_REGISTRY": registry,
        }
        if full:
            config = {"SHOWCASE_STAR_FULL_ENABLED": True,
                      "SHOWCASE_STAR_PYTHON_IMAGE_ID": self.IMAGE}
        self.open_star([replier] * 64, **config)
        job_id = self.create_job() if not full else self.submit_full()
        job = self.terminal(job_id)
        stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        events = [json.loads(line[6:]) for line in stream.splitlines()
                  if line.startswith("data: ")]
        return job_id, job, events

    def submit_full(self):
        response = self.client.post("/api/agent/jobs", json={
            "message": "1+1", "session_id": self.session, "solver_mode": "star_reference",
        }, headers=self.headers())
        self.assertEqual(202, response.status_code, response.get_json())
        return response.get_json()["job_id"]

    def planner_requests(self):
        return [item for item in self.outbound if item["role"] == "planner"]

    def public_events(self, events, solver_type):
        return [event for event in events if event.get("solver_event_type") == solver_type]

    def assert_public_boundary(self, job_id, events):
        serialized = json.dumps(events, ensure_ascii=False)
        report_text = json.dumps(self.report(job_id), ensure_ascii=False)
        for sentinel in ("REPLAN_TASK_SENTINEL", "OLD_DIRECTION", "NEW_DIRECTION"):
            self.assertNotIn(sentinel, serialized)
            self.assertNotIn(sentinel, report_text)

    def test_second_approval_keeps_its_own_directions_and_rescues(self):
        replier = star_replier({1: RULING_FIRST, 2: RULING_SECOND}, {("a2", 0)})
        job_id, job, events = self.run_public(replier)
        self.assertEqual("succeeded", job["status"], job)
        progress = job["result"]["solver"]["progress"]
        self.assertEqual(3, progress["plan_version"], progress)
        # The replan Guidance entered an independent decision: a ruling meta call
        # (no guidance_request) precedes every archive.
        guidance_calls = [item for item in self.outbound if item["role"] == "meta"
                          and item.get("guidance_request") is not None]
        ruling_calls = [item for item in self.outbound if item["role"] == "meta"
                        and item.get("guidance_request") is None]
        self.assertEqual(1, len(guidance_calls), [item["role"] for item in self.outbound])
        self.assertEqual([1, 2], [item["plan_version"] for item in ruling_calls],
                         [item.get("plan_version") for item in ruling_calls])
        self.assertEqual("stuck",
                         guidance_calls[0]["guidance_request"]["failure_type"])
        archived = self.public_events(events, "plan_archived")
        self.assertEqual(2, len(archived), archived)
        approvals = [event for event in self.public_events(events, "meta_decided")
                     if event.get("decision") == "APPROVE_REPLAN"]
        self.assertEqual(2, len(approvals), approvals)
        # The archive records the ruling that authorized it.
        self.assertEqual([approvals[0]["solver_revision"], approvals[1]["solver_revision"]],
                         [event.get("decision_revision") for event in archived], archived)
        # The new Planner actually receives this ruling's directions and rescued work.
        final_planner = self.planner_requests()[-1]
        self.assertEqual(3, final_planner["plan_version"], final_planner)
        self.assertIn("NEW_DIRECTION", final_planner["forbidden_directions"])
        self.assertIn("OLD_DIRECTION", final_planner["forbidden_directions"])
        self.assertEqual({"A1_FACT", "B1_FACT"},
                         {item["statement"] for item in final_planner["accepted_results"]},
                         final_planner["accepted_results"])
        second_failure = final_planner["failure_records"][-1]
        self.assertEqual(("second route archived", ["NEW_DIRECTION"]),
                         (second_failure["reason"], second_failure["forbidden_directions"]),
                         second_failure)
        self.assertEqual({"A1_FACT", "B1_FACT"},
                         {item["statement"] for item in second_failure["rescued_results"]},
                         second_failure)
        # The stale Guidance never regains authority and stays out of public text.
        self.assert_public_boundary(job_id, events)
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        self.assertEqual(2, len([event for event in evidence["timeline"]
                                 if event.get("solver_event_type") == "plan_archived"
                                 and "decision_revision" in event]), evidence["timeline"])

    def test_replan_decision_continue_keeps_the_plan_and_actually_continues(self):
        # Plan-version 2 ruling only exists so the unfixed flow (which replaces the
        # plan straight from Guidance) can finish; the fixed flow never consults it.
        replier = star_replier({1: RULING_CONTINUE, 2: RULING_CONTINUE}, {("a1", 0)})
        job_id, job, events = self.run_public(replier)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual([], self.public_events(events, "plan_archived"),
                         self.public_events(events, "plan_archived"))
        self.assertEqual([], self.public_events(events, "plan_replaced"))
        progress = job["result"]["solver"]["progress"]
        self.assertEqual(1, progress["plan_version"], progress)
        # The decision, not the Guidance, ruled: one guidance call then one ruling.
        ruling_calls = [item for item in self.outbound if item["role"] == "meta"
                        and item.get("guidance_request") is None]
        self.assertEqual([1], [item["plan_version"] for item in ruling_calls])
        decided = [event for event in self.public_events(events, "meta_decided")
                   if event.get("decision") == "CONTINUE"]
        self.assertEqual(1, len(decided), decided)
        self.assertEqual(1, decided[0].get("attempt_index"), decided)
        # CONTINUE actually continues: the step re-dispatches under a new action
        # identity, and no replacement Planner was ever dispatched.
        reasoners = [item for item in self.outbound if item["role"] == "reasoner"]
        self.assertEqual([(0, "a1"), (1, "a1"), (1, "a2")],
                         [(item["role_context"]["state"]["attempt_index"],
                           item["step"]["step_id"]) for item in reasoners],
                         [item["call_id"] for item in reasoners])
        self.assertEqual(1, len(self.planner_requests()), self.planner_requests())
        self.assert_public_boundary(job_id, events)

    def test_replan_decision_abort_stops_without_planner_or_archive(self):
        # Same as above: the version-2 ruling only serves the unfixed direct-replace flow.
        replier = star_replier({1: RULING_ABORT, 2: RULING_ABORT}, {("a1", 0)})
        job_id, job, events = self.run_public(replier)
        self.assertEqual("failed", job["status"], job)
        self.assertEqual("partial_aborted", job["result"]["solver"]["status"], job)
        self.assertIn(RULING_ABORT["reason_summary"], job["result"]["final_response"])
        self.assertEqual([], self.public_events(events, "plan_archived"))
        self.assertEqual([], self.public_events(events, "plan_replaced"))
        decided = [event for event in self.public_events(events, "meta_decided")
                   if event.get("decision") == "ABORT"]
        self.assertEqual(1, len(decided), decided)
        # ABORT never dispatches a replacement Planner; only the initial plan remains.
        self.assertEqual(1, len(self.planner_requests()), self.planner_requests())
        self.assertEqual(1, len([item for item in self.outbound
                                 if item["role"] == "meta"
                                 and item.get("guidance_request") is None]))

    def test_bypassing_the_approval_gate_reproduces_the_stale_guidance_archive(self):
        from showcase.solver_harness import replan as replan_module

        def synthesized_ruling(run, state):
            guidance = state["meta_guidance_decision"]
            return {"reason_summary": guidance["rationale"],
                    "forbidden_directions": [], "reusable_results": []}

        with patch.object(replan_module, "replan_ruling", synthesized_ruling):
            replier = star_replier({1: RULING_FIRST, 2: RULING_SECOND}, {("a2", 0)})
            job_id, job, events = self.run_public(replier)
        # Deliberately re-synthesizing the approval from the stale Guidance loses the
        # new ruling's directions and rescue work: the exact defect this ticket fixes.
        final_planner = self.planner_requests()[-1]
        self.assertNotIn("NEW_DIRECTION", final_planner["forbidden_directions"])
        self.assertEqual([], final_planner["accepted_results"], final_planner)
        self.assertEqual(GUIDANCE_REPLAN["rationale"],
                         final_planner["failure_records"][-1]["reason"])

    def assert_replan_recovery_window(self):
        """Crash after the replan Guidance commit; resume rules exactly once."""
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            process = subprocess.run([sys.executable, "-m", "tests.star_recovery_worker",
                                      directory, "replan_guidance_decided"],
                                     capture_output=True, timeout=90)
            self.assertEqual(71, process.returncode, process.stderr.decode(errors="replace"))
            job_id = (folder / "job_id").read_text()
            before = [json.loads(line) for line in
                      (folder / "requests.jsonl").read_text().splitlines()]
            with patch.dict(os.environ, {"INTERN_API_KEY": "scripted-only"}), patch(
                    "llm_client.requests.post",
                    side_effect=lambda *a, **kw: worker_provider(folder, kw)):
                from showcase.flask_app import create_app

                app = create_app(worker_config(folder))
                try:
                    self.app = app
                    self.client = app.test_client()
                    self.csrf = self.client.get("/api/check_auth").get_json()["csrf_token"]
                    original = self.job(job_id)["result"]["budget"]
                    response = self.client.post(f"/api/agent/jobs/{job_id}/resume",
                                                json={}, headers=self.headers())
                    self.assertEqual(202, response.status_code, response.get_json())
                    final = self.terminal(job_id)
                    self.assertEqual("succeeded", final["status"], final)
                    after = [json.loads(line) for line in
                             (folder / "requests.jsonl").read_text().splitlines()]
                    # The resumed run never re-dispatches a request already sent, and
                    # the ReplanDecision is consulted exactly once on the fresh run.
                    self.assertEqual(before, after[:len(before)])
                    self.assertEqual(2, sum(item["role"] == "meta" for item in after))
                    replacement = next(item for item in after[len(before):]
                                       if item["role"] == "planner"
                                       and item.get("plan_version") == 2)
                    self.assertEqual(["WORKER_DIRECTION"], replacement["forbidden_directions"])
                    stream = self.client.get(
                        f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
                    events = [json.loads(line[6:]) for line in stream.splitlines()
                              if line.startswith("data: ")]
                    archived = [event for event in events
                                if event.get("solver_event_type") == "plan_archived"]
                    approvals = [event for event in events
                                 if event.get("solver_event_type") == "meta_decided"
                                 and event.get("decision") == "APPROVE_REPLAN"]
                    self.assertEqual(1, len(archived), archived)
                    self.assertEqual(1, len(approvals), approvals)
                    self.assertEqual(approvals[0]["solver_revision"],
                                     archived[0].get("decision_revision"), archived)
                    self.assertEqual(original["deadline_at"],
                                     final["result"]["budget"]["deadline_at"])
                    self.assertEqual(original["reserved_tokens"],
                                     final["result"]["budget"]["reserved_tokens"])
                finally:
                    for name in ("showcase_workspace_service", "showcase_run_service",
                                 "loopback_store"):
                        app.extensions[name].close()

    def test_recovery_after_replan_guidance_rules_exactly_once(self):
        self.assert_replan_recovery_window()

    @unittest.skipUnless(IMAGE, "requires independently validated local Docker image ID")
    def test_reference_preset_rulings_cover_all_three_branches(self):
        # The complete reference preset runs the same public acceptance with real
        # isolated admission: CONTINUE keeps the plan, ABORT stops without a planner,
        # APPROVE_REPLAN archives with its own directions and rescue work.
        with self.subTest(branch="continue"):
            replier = star_replier({1: RULING_CONTINUE}, {("a1", 0)})
            job_id, job, events = self.run_public(replier, full=True)
            self.assertEqual("succeeded", job["status"], job)
            self.assertEqual("star_reference", job["result"]["execution_mode"])
            self.assertEqual([], job["result"]["missing_capabilities"])
            self.assertEqual(1, job["result"]["solver"]["progress"]["plan_version"])
            self.assertEqual([], self.public_events(events, "plan_archived"))
        with self.subTest(branch="abort"):
            replier = star_replier({1: RULING_ABORT}, {("a1", 0)})
            job_id, job, events = self.run_public(replier, full=True)
            self.assertEqual("failed", job["status"], job)
            self.assertEqual("partial_aborted", job["result"]["solver"]["status"], job)
            self.assertEqual(1, len(self.planner_requests()), self.planner_requests())
            self.assertEqual([], self.public_events(events, "plan_archived"))
        with self.subTest(branch="approve_replan"):
            replier = star_replier({1: RULING_FIRST, 2: RULING_SECOND}, {("a2", 0)})
            job_id, job, events = self.run_public(replier, full=True)
            self.assertEqual("succeeded", job["status"], job)
            self.assertEqual(3, job["result"]["solver"]["progress"]["plan_version"])
            archived = self.public_events(events, "plan_archived")
            approvals = [event for event in self.public_events(events, "meta_decided")
                         if event.get("decision") == "APPROVE_REPLAN"]
            self.assertEqual(2, len(archived), archived)
            self.assertEqual([approvals[0]["solver_revision"], approvals[1]["solver_revision"]],
                             [event.get("decision_revision") for event in archived], archived)
            final_planner = self.planner_requests()[-1]
            self.assertIn("NEW_DIRECTION", final_planner["forbidden_directions"])
            self.assertEqual({"A1_FACT", "B1_FACT"},
                             {item["statement"] for item in final_planner["accepted_results"]},
                             final_planner["accepted_results"])


if __name__ == "__main__":
    unittest.main()
