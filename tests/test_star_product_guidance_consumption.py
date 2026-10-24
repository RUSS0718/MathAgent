"""Trace-Back only consumes the ruling attached to the current transition (ALIGN-AC-01)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from showcase.run_budget import RunBudgetLimits
from showcase.tools import ToolRegistry
from tests.star_product_support import ACCEPT, StarJobFixture
from tests.star_recovery_worker import config as worker_config, provider as worker_provider
from tests.test_star_product_challenge import META_ABORT
from tests.test_star_product_tools import FEATURES, NEED_PLAN, VERDICT

PLAN = {"version": 1, "steps": [
    {"step_id": "s1", "title": "First", "objective": "Establish the base fact"},
    {"step_id": "s2", "title": "Second", "objective": "Extend the fact", "depends_on": ["s1"]},
    {"step_id": "s3", "title": "Third", "objective": "Conclude", "depends_on": ["s2"]},
]}
GUIDANCE_TRACE_1 = {
    "action_type": "trace_back", "specific_task": "REDO_FROM_SENTINEL",
    "use_pure_reasoning": False, "trace_back_to": 1,
    "rationale": "Retry from the first step",
}
META_TRACE_2 = {
    **META_ABORT, "decision": "TRACE_BACK", "reason_summary": "The rebuilt route also failed",
    "plan_summary": "Rebuild from the second step", "trace_back_to": 2,
}
PROPOSE = {"goal_gate": "NO", "logic_gate": "FAIL", "verdict": "PROPOSE_REPLAN",
           "objection": "The conclusion does not follow"}


def report(argument, **extra):
    return {"argument": argument, "claims": [], "blocked": False, **extra}


REPLIES = [
    NEED_PLAN, PLAN,
    report("first fact"), VERDICT,
    report("second attempt", blocked=True),
    GUIDANCE_TRACE_1,
    report("first fact again"), VERDICT,
    report("second fact"), VERDICT,
    report("third attempt"), PROPOSE,
    META_TRACE_2,
    report("second fact again"), VERDICT,
    report("third fact"), VERDICT,
    {"final_response": "2"}, ACCEPT,
]


class StarGuidanceConsumptionTest(StarJobFixture, unittest.TestCase):
    IMAGE = os.environ.get("MATHAGENT_TEST_PYTHON_IMAGE")

    def run_public(self, replies):
        registry = ToolRegistry()
        registry.register("polynomial_check", lambda _args: None)
        self.open_star(replies, SHOWCASE_STAR_FEATURES={**FEATURES, "meta_guidance": True},
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=28, max_http_attempts=28),
                       SHOWCASE_STAR_REGISTRY=registry)
        return self.finish_public_job()

    def finish_public_job(self):
        job_id = self.create_job()
        job = self.terminal(job_id)
        stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        events = [json.loads(line[6:]) for line in stream.splitlines() if line.startswith("data: ")]
        return job_id, job, events

    def submit_full(self):
        response = self.client.post("/api/agent/jobs", json={
            "message": "1+1", "session_id": self.session, "solver_mode": "star_reference",
        }, headers=self.headers())
        self.assertEqual(202, response.status_code, response.get_json())
        return response.get_json()["job_id"]

    @staticmethod
    def applied_events(events):
        return [e for e in events if e.get("solver_event_type") == "trace_back_applied"]

    def test_second_traceback_consumes_only_the_new_meta_ruling(self):
        job_id, job, events = self.run_public(list(REPLIES))
        applied = self.applied_events(events)
        self.assertEqual(2, len(applied), applied)
        first, second = applied
        # The first ruling is the fresh Guidance; the second must be the new Meta decision.
        self.assertEqual((1, "meta_guidance"), (first["trace_back_to"], first["triggered_by"]))
        self.assertEqual((2, "meta"), (second["trace_back_to"], second["triggered_by"]))
        self.assertEqual((3, 2, 1, 1), tuple(second.get(key) for key in (
            "from_step_index", "archived_step_count", "invalidated_result_count",
            "rescued_result_count")), second)
        # The ruling source is verifiable against the committed decision revision.
        guidance_decided = next(event for event in events
                                if event.get("solver_revision") == first["decision_revision"])
        self.assertEqual("meta_guidance_decided", guidance_decided["solver_event_type"])
        decided = next(event for event in events
                       if event.get("solver_revision") == second["decision_revision"])
        self.assertEqual("meta_decided", decided["solver_event_type"])
        self.assertEqual("succeeded", job["status"], job)
        # The second archive keeps step 1 and its accepted result; the retry resumes at step 2.
        reasoners = [item for item in self.outbound if item["role"] == "reasoner"]
        self.assertEqual(7, len(reasoners), [item["call_id"] for item in reasoners])
        retry = reasoners[5]
        self.assertEqual(("s2", 2, 1), (retry["step"]["step_id"],
                                        retry["role_context"]["state"]["attempt_index"],
                                        retry["role_context"]["state"]["plan_version"]))
        failure = retry["failure_records"][-1]
        self.assertEqual(({"s2", "s3"}, 2, "meta"),
                         (set(failure["archived_steps"]), failure["trace_back_to"],
                          failure["triggered_by"]))
        self.assertEqual(["second fact"],
                         [item["statement"] for item in failure["invalidated_results"]])
        self.assertEqual(["first fact again"],
                         [item["statement"] for item in retry["rescued_results"]])
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        evidence_applied = [event for event in evidence["timeline"]
                            if event.get("solver_event_type") == "trace_back_applied"]
        self.assertEqual([(1, "meta_guidance"), (2, "meta")],
                         [(event.get("trace_back_to"), event.get("triggered_by"))
                          for event in evidence_applied], evidence_applied)
        self.assertNotIn("REDO_FROM_SENTINEL", json.dumps(events))
        self.assertNotIn("REDO_FROM_SENTINEL", json.dumps(self.report(job_id), ensure_ascii=False))

    def test_bypassing_the_consumption_gate_reproduces_stale_preemption(self):
        from showcase.solver_harness import traceback as traceback_module

        with patch.object(traceback_module, "transition_decision", lambda *arguments: True):
            job_id, job, events = self.run_public(list(REPLIES))
        applied = self.applied_events(events)
        self.assertEqual(2, len(applied), applied)
        # Deliberately bypassing the current-transition gate lets the consumed Guidance
        # preempt the new ruling: the second archive wrongly targets 1 again.
        self.assertEqual((1, "meta_guidance"),
                         (applied[1]["trace_back_to"], applied[1]["triggered_by"]), applied)
        self.assertNotEqual("succeeded", job["status"], job)

    def assert_process_window(self, window):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            process = subprocess.run([sys.executable, "-m", "tests.star_recovery_worker",
                                      directory, window], capture_output=True, timeout=90)
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
                    stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
                    events = [json.loads(line[6:]) for line in stream.splitlines()
                              if line.startswith("data: ")]
                    applied = self.applied_events(events)
                    self.assertEqual([(1, "meta_guidance"), (2, "meta")],
                                     [(event.get("trace_back_to"), event.get("triggered_by"))
                                      for event in applied], applied)
                    # The resumed run never re-dispatches a request already sent.
                    self.assertEqual(before, after[:len(before)])
                    self.assertEqual(original["deadline_at"],
                                     final["result"]["budget"]["deadline_at"])
                    self.assertEqual(original["reserved_tokens"],
                                     final["result"]["budget"]["reserved_tokens"])
                    return before, after
                finally:
                    for name in ("showcase_workspace_service", "showcase_run_service",
                                 "loopback_store"):
                        app.extensions[name].close()

    @unittest.skipUnless(IMAGE, "requires independently validated local Docker image ID")
    def test_reference_preset_second_traceback_consumes_only_the_new_meta_ruling(self):
        # The same public acceptance under the complete reference preset: real isolated
        # admission, every core feature on, and the second ruling still wins.
        self.open_star(list(REPLIES), SHOWCASE_STAR_FULL_ENABLED=True,
                       SHOWCASE_STAR_PYTHON_IMAGE_ID=self.IMAGE)
        job_id = self.submit_full()
        job = self.terminal(job_id)
        stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        events = [json.loads(line[6:]) for line in stream.splitlines() if line.startswith("data: ")]
        applied = self.applied_events(events)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual("star_reference", job["result"]["execution_mode"])
        self.assertEqual([], job["result"]["missing_capabilities"])
        self.assertEqual([(1, "meta_guidance"), (2, "meta")],
                         [(event.get("trace_back_to"), event.get("triggered_by"))
                          for event in applied], applied)

    def test_recovery_after_guidance_decision_applies_it_exactly_once(self):
        before, after = self.assert_process_window("guidance_decided")
        self.assertEqual(6, len(before))
        self.assertEqual(2, sum(item["role"] == "meta" for item in after))

    def test_recovery_after_meta_ruling_applies_it_exactly_once(self):
        before, after = self.assert_process_window("meta_decided")
        self.assertEqual(13, len(before))
        # The second ruling was dispatched before the crash and must not repeat.
        self.assertEqual(2, sum(item["role"] == "meta" for item in after))


if __name__ == "__main__":
    unittest.main()
