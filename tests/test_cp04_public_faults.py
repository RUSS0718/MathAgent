"""CP-04 faults through public Jobs with the Reasoner checkpoint flag enabled."""

import json
import requests
import sqlite3
import threading
import unittest
import uuid
from pathlib import Path

from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import ACCEPT, StarJobFixture
from tests.test_star_product_tools import NEED_PLAN, PLAN, VERDICT

FEATURES = {"final_generation": True, "final_solution_review": True,
            "reasoner_checkpoints": True}
OBJECTION = "Prove the missing implication rather than restating the result"
CHALLENGE = {"goal_gate": "PARTIAL", "logic_gate": "UNCERTAIN",
             "verdict": "CHALLENGE", "objection": OBJECTION}
TRACE_BACK = {"goal_gate": "NO", "logic_gate": "FAIL",
              "verdict": "TRACE_BACK", "trace_back_to": 2,
              "objection": "The old route is unsupported"}
REPLAN_GUIDANCE = {
    "action_type": "replan", "specific_task": "choose a new route",
    "use_pure_reasoning": False, "trace_back_to": None,
    "rationale": "The old route cannot finish",
}
APPROVE_REPLAN = {
    "decision": "APPROVE_REPLAN", "reason_summary": "Replace the old route",
    "plan_summary": "Use the direct route", "forbidden_directions": ["old route"],
    "reusable_results": ["safe reviewed fact"], "trace_back_to": None,
}

TRACE_PLAN = {"version": 1, "steps": [
    {"step_id": "independent", "title": "Known", "objective": "Establish safe fact"},
    {"step_id": "wrong", "title": "Route", "objective": "Try old route"},
    {"step_id": "dependent", "title": "Use", "objective": "Use old route",
     "depends_on": ["wrong"]},
    {"step_id": "finish", "title": "Finish", "objective": "Complete",
     "depends_on": ["dependent"]},
]}
REPLAN_PLANS = {
    1: {"version": 1, "steps": [
        {"step_id": "a1", "title": "Base", "objective": "Establish the base fact"},
        {"step_id": "a2", "title": "Route", "objective": "Use the old route",
         "depends_on": ["a1"]},
    ]},
    2: {"version": 2, "steps": [
        {"step_id": "b1", "title": "Direct", "objective": "Use the direct route"},
    ]},
}


def checkpoint(context, argument, *, status="FINAL", claims=None):
    """Script a reply against the actual step and call identity on the wire."""
    return {"checkpoint": {
        "protocol_version": 1, "checkpoint_id": context["call_id"] + "-reply",
        "status": status, "objective": context["step"]["objective"],
        "argument": argument, "claims": claims or [], "blocked": False,
        "dependencies": [], "evidence": [],
        "gaps": ["missing implication"] if status == "YIELD" else [],
        "next_action": "Prove the remaining implication",
    }}


def fact_checkpoint(context, statement):
    return checkpoint(
        context, statement,
        claims=[{"statement": statement, "label": "hard-verify"}],
    )


class CP04PublicFaultTest(StarJobFixture, unittest.TestCase):
    def open_checkpoint_job(self, replies):
        """Only provider HTTP is scripted; Job, review and storage are real."""
        self.open_star(replies, SHOWCASE_STAR_FEATURES=FEATURES,
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                           max_model_calls=28, max_http_attempts=28))

    def events(self, job_id):
        stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        return [json.loads(line[6:]) for line in stream.splitlines()
                if line.startswith("data: ")]

    def test_yield_verifier_objection_reaches_next_reasoner_before_final_review(self):
        self.open_checkpoint_job([
            NEED_PLAN, PLAN,
            lambda ctx: checkpoint(ctx, "partial proof", status="YIELD"), CHALLENGE,
            lambda ctx: checkpoint(ctx, "completed proof"), VERDICT,
            {"final_response": "2"}, ACCEPT,
        ])
        job_id = self.create_job()
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"], final)
        first, second = [r for r in self.outbound if r["role"] == "reasoner"]
        self.assertTrue(first["checkpoint_protocol"])
        self.assertEqual((1, 2), (first["checkpoint_round"], second["checkpoint_round"]))
        self.assertEqual(first["call_id"] + "-reply", second["parent_checkpoint_id"])
        self.assertEqual(OBJECTION, second["objection"])
        self.assertEqual(OBJECTION, second["feedback"]["objection"])
        reviews = [r for r in self.outbound if r["role"] == "step_verifier"]
        self.assertEqual(["YIELD", "FINAL"], [r["checkpoint"]["status"] for r in reviews])
        self.assertEqual("accepted", self.report(job_id)["semantics"]["whole_review"])
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        self.assertTrue(any(e.get("checkpoint_status") == "YIELD"
                            for e in evidence["timeline"]))
        event_types = [e.get("solver_event_type") for e in evidence["timeline"]]
        self.assertLess(event_types.index("step_reported"),
                        event_types.index("step_reviewed"))
        self.assertIn("challenge_dispatched", event_types)
        self.assertEqual(8, final["result"]["budget"]["http_attempts"])

    def test_cancel_during_reasoner_checkpoint_does_not_reach_verifier(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def paused(context):
            entered.set()
            release.wait(5)
            return checkpoint(context, "partial proof", status="YIELD")

        self.open_checkpoint_job([NEED_PLAN, PLAN, paused])
        job_id = self.create_job()
        self.assertTrue(entered.wait(5))
        self.assertEqual("canceled", self.cancel(job_id)["status"])
        release.set()
        final = self.terminal(job_id)
        self.assertEqual("canceled", final["status"], final)
        self.assertEqual(3, len(self.outbound))
        self.assertFalse(any(item["role"] == "step_verifier" for item in self.outbound))
        self.assertIn("event: canceled",
                      self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True))

    def test_resume_rejects_old_revision_after_reasoner_checkpoint_unknown(self):
        self.open_checkpoint_job([
            NEED_PLAN, PLAN, lambda context: fact_checkpoint(context, "checkpointed fact"),
            requests.Timeout("unknown verifier outcome"),
        ])
        job_id = self.create_job()
        failed = self.terminal(job_id)
        self.assertEqual("failed", failed["status"], failed)
        unknown = failed["result"]["solver"]["recovery"]["unknown_calls"]
        self.assertEqual(1, len(unknown))
        old_call_id = unknown[0]["call_id"]

        connection = sqlite3.connect(str(Path(self.data_dir) / "showcase.sqlite3"))
        try:
            connection.execute("UPDATE solver_states SET state_revision=999, "
                               "state_json=json_set(state_json,'$.state_revision',999)")
            connection.commit()
        finally:
            connection.close()

        response = self.client.post(
            f"/api/agent/jobs/{job_id}/resume",
            json={"retry_call": {"call_id": old_call_id, "new_call_id": str(uuid.uuid4())}},
            headers=self.headers(),
        )
        self.assertEqual(409, response.status_code, response.get_json())
        self.assertEqual("star_recovery_revision_unavailable", response.get_json()["error"])
        self.assertEqual("failed", self.job(job_id)["status"])
        self.assertEqual(4, len(self.outbound))

    def test_traceback_with_reasoner_checkpoints_excludes_invalidated_results(self):
        def checked(statement):
            return lambda context: fact_checkpoint(context, statement)

        self.open_star([
            NEED_PLAN, TRACE_PLAN,
            checked("safe reviewed fact"), {"goal_gate": "YES", "logic_gate": "PASS",
                                             "verdict": "ACCEPT", "objection": ""},
            checked("old wrong fact"), {"goal_gate": "YES", "logic_gate": "PASS",
                                         "verdict": "ACCEPT", "objection": ""},
            checked("old dependent fact"), {"goal_gate": "YES", "logic_gate": "PASS",
                                            "verdict": "ACCEPT", "objection": ""},
            checked("old completion"), TRACE_BACK,
            checked("new route"), {"goal_gate": "YES", "logic_gate": "PASS",
                                   "verdict": "ACCEPT", "objection": ""},
            checked("new dependent"), {"goal_gate": "YES", "logic_gate": "PASS",
                                       "verdict": "ACCEPT", "objection": ""},
            checked("new completion"), {"goal_gate": "YES", "logic_gate": "PASS",
                                        "verdict": "ACCEPT", "objection": ""},
            {"final_response": "2"}, ACCEPT,
        ], SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=32, max_http_attempts=32))
        job_id = self.create_job()
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"], final)
        reasoners = [item for item in self.outbound if item["role"] == "reasoner"]
        self.assertEqual(7, len(reasoners))
        self.assertEqual("wrong", reasoners[4]["step"]["step_id"])
        self.assertEqual(["safe reviewed fact"],
                         [item["statement"] for item in reasoners[4]["valid_sources"]])
        final_review = next(item for item in self.outbound
                            if item["role"] == "whole_solution_verifier")
        statements = [item["statement"] for item in final_review["accepted_results"]]
        self.assertIn("safe reviewed fact", statements)
        self.assertIn("new route", statements)
        self.assertIn("new dependent", statements)
        self.assertIn("new completion", statements)
        self.assertNotIn("old wrong fact", statements)
        self.assertNotIn("old dependent fact", statements)
        self.assertTrue(any(item.get("solver_event_type") == "trace_back_applied"
                            for item in self.events(job_id)))

    def test_approved_replan_decision_dispatches_new_plan_with_reasoner_checkpoints(self):
        reviews = {}

        def reply(context):
            role = context["role"]
            if role == "explore":
                return NEED_PLAN
            if role == "planner":
                return REPLAN_PLANS[context["plan_version"]]
            if role == "reasoner":
                step_id = context["step"]["step_id"]
                return fact_checkpoint(context, f"{step_id} checkpoint")
            if role == "step_verifier":
                step_id = context["step"]["step_id"]
                seen = reviews.get(step_id, 0)
                reviews[step_id] = seen + 1
                if step_id == "a2" and seen == 0:
                    return {"goal_gate": "NO", "logic_gate": "FAIL",
                            "verdict": "PROPOSE_REPLAN", "objection": "old route fails"}
                return {"goal_gate": "YES", "logic_gate": "PASS",
                        "verdict": "ACCEPT", "objection": ""}
            if role == "meta":
                return REPLAN_GUIDANCE if context.get("guidance_request") is not None else APPROVE_REPLAN
            if role == "final_generator":
                return {"final_response": "2"}
            return ACCEPT

        self.open_star([reply] * 32,
                       SHOWCASE_STAR_FEATURES={**FEATURES, "meta_guidance": True},
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=28, max_http_attempts=28))
        job_id = self.create_job()
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"], final)
        planners = [item for item in self.outbound if item["role"] == "planner"]
        self.assertEqual(2, len(planners))
        self.assertEqual(2, planners[-1]["plan_version"])
        self.assertEqual("b1", [item for item in self.outbound if item["role"] == "reasoner"][-1]
                         ["step"]["step_id"])
        events = self.events(job_id)
        self.assertTrue(any(item.get("solver_event_type") == "meta_decided"
                            and item.get("decision") == "APPROVE_REPLAN"
                            for item in events))
        self.assertTrue(any(item.get("solver_event_type") == "plan_archived"
                            for item in events))
        self.assertTrue(any(item.get("solver_event_type") == "plan_replaced"
                            for item in events))

    def test_process_reopen_reuses_reasoner_checkpoint_and_tool_receipt_once(self):
        import os
        import subprocess
        import sys
        import tempfile
        import time
        from unittest.mock import patch

        from showcase.flask_app import create_app
        from tests.cp04_reasoner_worker import config as worker_config
        from tests.cp04_reasoner_worker import provider as worker_provider

        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            process = subprocess.run(
                [sys.executable, "-m", "tests.cp04_reasoner_worker", directory],
                capture_output=True, timeout=35,
            )
            self.assertEqual(71, process.returncode,
                             process.stderr.decode(errors="replace"))
            job_id = (folder / "job_id").read_text(encoding="utf-8")
            before = [json.loads(line) for line in
                      (folder / "requests.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(["explore", "planner", "reasoner", "step_verifier"],
                             [item["role"] for item in before])
            self.assertEqual(1, len((folder / "tool_runs.txt").read_text().splitlines()))

            with patch.dict(os.environ, {"INTERN_API_KEY": "scripted-only"}), patch(
                    "llm_client.requests.post",
                    side_effect=lambda *args, **kwargs: worker_provider(folder, kwargs)):
                app = create_app(worker_config(folder))
                try:
                    client = app.test_client()
                    csrf = client.get("/api/check_auth").get_json()["csrf_token"]
                    headers = {"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())}
                    before_job = client.get(f"/api/agent/jobs/{job_id}").get_json()
                    original_budget = before_job["result"]["budget"]
                    resumed = client.post(f"/api/agent/jobs/{job_id}/resume",
                                          json={}, headers=headers)
                    self.assertEqual(202, resumed.status_code, resumed.get_json())
                    duplicate = client.post(f"/api/agent/jobs/{job_id}/resume",
                                             json={}, headers=headers)
                    self.assertEqual(200, duplicate.status_code, duplicate.get_json())
                    deadline = time.monotonic() + 12
                    while time.monotonic() < deadline:
                        job = client.get(f"/api/agent/jobs/{job_id}").get_json()
                        if job["status"] in {"succeeded", "failed", "canceled"}:
                            break
                        time.sleep(.02)
                    self.assertEqual("succeeded", job["status"], job)
                    final_budget = job["result"]["budget"]
                    after = [json.loads(line) for line in
                             (folder / "requests.jsonl").read_text(encoding="utf-8").splitlines()]
                    self.assertEqual(before, after[:len(before)])
                    self.assertEqual(before[-1]["call_id"], after[len(before) - 1]["call_id"])
                    self.assertNotIn(before[-1]["call_id"],
                                     [item["call_id"] for item in after[len(before):]])
                    self.assertEqual(original_budget["deadline_at"], final_budget["deadline_at"])
                    self.assertEqual(original_budget["logical_calls"] + 4,
                                     final_budget["logical_calls"])
                    self.assertEqual(original_budget["http_attempts"] + 4,
                                     final_budget["http_attempts"])
                    self.assertEqual(original_budget["provider_known"]["total_tokens"] + 40,
                                     final_budget["provider_known"]["total_tokens"])
                    self.assertEqual(0, final_budget["reserved_tokens"])
                    self.assertEqual(1, len((folder / "tool_runs.txt").read_text().splitlines()))
                    self.assertEqual(1, final_budget["tool_calls"])
                    self.assertEqual(1, len(job["result"]["tool_results"]))
                    self.assertEqual("success", job["result"]["tool_results"][0]["status"])
                    self.assertEqual(2, sum(item["role"] == "reasoner" for item in after))
                    stream = client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
                    events = [json.loads(line[6:]) for line in stream.splitlines()
                              if line.startswith("data: ")]
                    reported = [item for item in events
                                if item.get("solver_event_type") == "step_reported"]
                    self.assertTrue(any(item.get("checkpoint_status") == "YIELD"
                                        for item in reported))
                    self.assertTrue(any(item.get("checkpoint_status") == "FINAL"
                                        for item in reported))
                finally:
                    for name in ("showcase_workspace_service", "showcase_run_service",
                                 "loopback_store"):
                        app.extensions[name].close()


if __name__ == "__main__":
    unittest.main()
