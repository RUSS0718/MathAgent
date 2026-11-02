"""首次 PROPOSE_REPLAN 后 Meta CONTINUE 必须以新动作身份实际派发(公共 Job)。

覆盖 ALIGN-AC-03：首次审查直接 PROPOSE_REPLAN、Meta 返回 CONTINUE 后，
同一 Job 在预算充足时实际派发下一次 Reasoner 并完成后续审查，不因事件
身份冲突失败；已有 Challenge 历史后的 CONTINUE 保持历史与异议连续；
动作提交及恢复边界沿用已完成动作身份并复用已核验结果。
"""

import json
import os
import subprocess
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import ACCEPT, StarJobFixture
from tests.test_star_product_tools import NEED_PLAN, PLAN, VERDICT

STEP = {"argument": "addition", "blocked": False,
        "claims": [{"statement": "1+1=2", "label": "hard-verify"}]}
STEP_RETRY = {"argument": "addition with carrying", "blocked": False,
              "claims": [{"statement": "1+1=2", "label": "hard-verify"}]}
PROPOSE_REPLAN = {"goal_gate": "NO", "logic_gate": "FAIL", "verdict": "PROPOSE_REPLAN",
                  "objection": "The argument never justifies carrying."}
META_CONTINUE = {"decision": "CONTINUE",
                 "reason_summary": "Re-solve the same step against the objection.",
                 "plan_summary": "Keep the current plan.", "forbidden_directions": [],
                 "reusable_results": [], "trace_back_to": None}
CHALLENGE_ONE = {"goal_gate": "PARTIAL", "logic_gate": "UNCERTAIN",
                 "verdict": "CHALLENGE", "objection": "Check the boundary case."}
CHALLENGE_TWO = {"goal_gate": "PARTIAL", "logic_gate": "UNCERTAIN",
                 "verdict": "CHALLENGE", "objection": "Check the equality case."}
HIDDEN_ARGUMENT = "private hidden reasoning must stay out of public events"
FEATURES = {"final_generation": True, "final_solution_review": True}
IMAGE = os.environ.get("MATHAGENT_TEST_PYTHON_IMAGE")


class StarContinueIdentityTest(StarJobFixture, unittest.TestCase):
    def run_star(self, replies, budget=16):
        self.open_star(replies, SHOWCASE_STAR_FEATURES=FEATURES,
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                           max_model_calls=budget, max_http_attempts=budget))
        job_id = self.create_job()
        job = self.terminal(job_id)
        stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        events = [json.loads(line[6:])
                  for line in stream.splitlines() if line.startswith("data: ")]
        return job_id, job, events

    def test_first_propose_replan_with_meta_continue_dispatches_a_new_action(self):
        job_id, job, events = self.run_star([
            NEED_PLAN, PLAN, STEP, PROPOSE_REPLAN, META_CONTINUE,
            STEP_RETRY, VERDICT, {"final_response": "2"}, ACCEPT,
        ])
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual(["explore", "planner", "reasoner", "step_verifier", "meta",
                          "reasoner", "step_verifier", "final_generator",
                          "whole_solution_verifier"],
                         [request["role"] for request in self.outbound])
        # 新求解动作拥有独立调用身份；边界上能看到第二次真实派发。
        self.assertNotEqual(self.outbound[2]["call_id"], self.outbound[5]["call_id"])
        # 第二次审查消费的是新动作的实际报告，不是被驳回的旧报告。
        self.assertEqual("addition with carrying", self.outbound[6]["report"]["argument"])
        attempts = [item for item in job["result"]["request_attempts"]
                    if item["role"] == "reasoner"]
        self.assertEqual(2, len(attempts))
        self.assertEqual(2, len({item["solver_call_id"] for item in attempts}))
        decided = next(event for event in events
                       if event.get("solver_event_type") == "meta_decided")
        self.assertEqual("CONTINUE", decided.get("decision"))
        dispatched = [event for event in events
                      if event.get("solver_event_type") == "step_dispatched"]
        self.assertEqual(2, len(dispatched))
        self.assertEqual(2, len({event["solver_event_id"] for event in dispatched}))
        reported = [event for event in events
                    if event.get("solver_event_type") == "step_reported"]
        self.assertEqual(2, len(reported))
        self.assertEqual(9, self.report(job_id)["budget"]["logical_calls"])
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        timeline = [item.get("solver_event_type") for item in evidence["timeline"]]
        self.assertEqual(2, timeline.count("step_dispatched"))
        self.assertEqual(2, timeline.count("step_reviewed"))

    def test_continue_after_challenge_history_keeps_history_and_objection(self):
        job_id, job, events = self.run_star([
            NEED_PLAN, PLAN, STEP, CHALLENGE_ONE,
            {"argument": HIDDEN_ARGUMENT, "claims": [], "blocked": False}, CHALLENGE_TWO,
            {"argument": HIDDEN_ARGUMENT, "claims": [], "blocked": False}, PROPOSE_REPLAN,
            META_CONTINUE, STEP_RETRY, VERDICT, {"final_response": "2"}, ACCEPT,
        ])
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual(["explore", "planner", "reasoner", "step_verifier",
                          "reasoner", "step_verifier", "reasoner", "step_verifier",
                          "meta", "reasoner", "step_verifier", "final_generator",
                          "whole_solution_verifier"],
                         [request["role"] for request in self.outbound])
        resumed = self.outbound[9]
        self.assertEqual("reasoner", resumed["role"])
        # Challenge 历史及各轮具体异议保持连续地进入新动作请求。
        self.assertEqual([1, 2], [item["round"] for item in resumed["challenge_history"]])
        self.assertEqual(["Check the boundary case.", "Check the equality case."],
                         [item["objection"] for item in resumed["challenge_history"]])
        self.assertEqual("The argument never justifies carrying.", resumed["objection"])
        # 新动作仍是独立调用身份，且复审消费新报告。
        self.assertNotEqual(self.outbound[2]["call_id"], self.outbound[9]["call_id"])
        self.assertEqual("addition with carrying", self.outbound[10]["report"]["argument"])
        # 历史事件未被删除：先前轮次的公开时间线仍在。
        replied = [event for event in events
                   if event.get("solver_event_type") == "challenge_replied"]
        self.assertEqual([1, 2], [event.get("round") for event in replied])
        self.assertNotIn(HIDDEN_ARGUMENT, json.dumps(events, ensure_ascii=False))
        self.assertEqual(13, self.report(job_id)["budget"]["logical_calls"])

    def test_process_exit_after_meta_continue_resumes_with_new_action_identity(self):
        import os

        from showcase.flask_app import create_app
        from tests.star_recovery_worker import config, provider

        with __import__("tempfile").TemporaryDirectory() as directory:
            folder = Path(directory)
            process = subprocess.run(
                [sys.executable, "-m", "tests.star_recovery_worker", directory, "meta_continue"],
                capture_output=True, timeout=30)
            self.assertEqual(71, process.returncode, process.stderr.decode(errors="replace"))
            job_id = (folder / "job_id").read_text()
            before = [json.loads(line)
                      for line in (folder / "requests.jsonl").read_text().splitlines()]
            self.assertEqual(["explore", "planner", "reasoner", "step_verifier", "meta"],
                             [item["role"] for item in before])
            self.assertEqual("s1", before[3]["step"]["step_id"])
            with patch.dict(os.environ, {"INTERN_API_KEY": "scripted-only"}), patch(
                    "llm_client.requests.post", side_effect=lambda *a, **kw: provider(folder, kw)):
                app = create_app(config(folder))
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
                    after = [json.loads(line) for line in (folder / "requests.jsonl")
                             .read_text().splitlines()]
                    # 已完成动作没有重复外部派发；续算从新动作的 Reasoner 开始。
                    self.assertEqual(13, len(after))
                    self.assertEqual(["reasoner", "step_verifier", "reasoner",
                                      "step_verifier", "reasoner", "step_verifier",
                                      "final_generator", "whole_solution_verifier"],
                                     [item["role"] for item in after[5:]])
                    resumed_actions = [item["call_id"] for item in after[5:]
                                       if item["role"] == "reasoner"
                                       and item["step"]["step_id"] == "s1"]
                    self.assertEqual(1, len(resumed_actions))
                    self.assertNotEqual(before[2]["call_id"], resumed_actions[0])
                    self.assertEqual(original["deadline_at"],
                                     final["result"]["budget"]["deadline_at"])
                    self.assertEqual(13, final["result"]["budget"]["logical_calls"])
                    stream = self.client.get(f"/api/agent/jobs/{job_id}/events") \
                        .get_data(as_text=True)
                    events = [json.loads(line[6:]) for line in stream.splitlines()
                              if line.startswith("data: ")]
                    reviews = [event for event in events
                               if event.get("solver_event_type") == "step_reviewed"]
                    self.assertEqual(["PROPOSE_REPLAN", "ACCEPT", "ACCEPT", "ACCEPT"],
                                     [event.get("verdict") for event in reviews])
                finally:
                    for name in ("showcase_workspace_service", "showcase_run_service",
                                 "loopback_store"):
                        app.extensions[name].close()


@unittest.skipUnless(IMAGE, "requires independently validated local Docker image ID")
class StarFullReferenceContinueTest(StarJobFixture, unittest.TestCase):
    def test_reference_continue_completes_new_action_and_whole_review(self):
        self.open_star(
            [NEED_PLAN, PLAN, STEP, PROPOSE_REPLAN, META_CONTINUE,
             STEP_RETRY, VERDICT, {"final_response": "x^2 - 1 = (x - 1)(x + 1)."}, ACCEPT],
            SHOWCASE_STAR_FULL_ENABLED=True, SHOWCASE_STAR_PYTHON_IMAGE_ID=IMAGE)
        response = self.client.post("/api/agent/jobs", json={
            "message": "Factor x^2-1.", "session_id": self.session,
            "solver_mode": "star_reference"}, headers=self.headers())
        self.assertEqual(202, response.status_code, response.get_json())
        job = self.terminal(response.get_json()["job_id"])
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual("star_reference", job["result"]["execution_mode"])
        self.assertEqual([], job["result"]["missing_capabilities"])
        self.assertEqual(["explore", "planner", "reasoner", "step_verifier", "meta",
                          "reasoner", "step_verifier", "final_generator",
                          "whole_solution_verifier"],
                         [request["role"] for request in self.outbound])
        self.assertNotEqual(self.outbound[2]["call_id"], self.outbound[5]["call_id"])
        self.assertEqual("addition with carrying", self.outbound[6]["report"]["argument"])
        report = self.report(response.get_json()["job_id"])
        self.assertEqual(9, report["budget"]["logical_calls"])
        self.assertEqual(0, report["budget"]["tool_calls"])
        stream = self.client.get(
            f"/api/agent/jobs/{response.get_json()['job_id']}/events").get_data(as_text=True)
        events = [json.loads(line[6:])
                  for line in stream.splitlines() if line.startswith("data: ")]
        decided = next(event for event in events
                       if event.get("solver_event_type") == "meta_decided")
        self.assertEqual("CONTINUE", decided.get("decision"))
        self.assertEqual(1, decided.get("attempt_index"))
        self.assertEqual(2, len({event["solver_event_id"] for event in events
                                 if event.get("solver_event_type") == "step_dispatched"}))


if __name__ == "__main__":
    unittest.main()
