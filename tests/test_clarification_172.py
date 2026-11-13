"""Necessary clarification is consumed through the authenticated public Job API."""

import json
import unittest
from unittest.mock import patch

from tests import test_faithful_service_job as service_tests
from tests.star_product_support import ACCEPT, StarJobFixture

PROBLEM = "求这个三角形的数值面积。"
SPEC = {
    "specification_version": 1, "original_problem": PROBLEM,
    "domain": "Euclidean triangle", "quantifiers": [], "assumptions": [],
    "directions": [], "output_requirements": ["数值面积"],
    "root_obligations": [{"obligation_id": "area", "obligation_type": "universal",
                          "statement": "计算三角形数值面积"}],
    "auxiliary_goals": [],
    "clarification": {"question": "请提供底边长度和对应的高（含单位）。",
                      "reason": "数值面积取决于尚未给出的尺寸，不能从当前条件确定。"},
}


class ClarificationTest(StarJobFixture, unittest.TestCase):
    open_faithful = service_tests.FaithfulServiceJobTest.open_faithful

    def open_star(self, replies, **config):
        super().open_star(replies, SHOWCASE_PRESENTATION_ENABLED=True, **config)

    def waiting(self):
        self.open_faithful([SPEC])
        created = self.client.post("/api/agent/jobs", headers=self.headers(),
            json={"session_id": self.session, "message": PROBLEM, "presentation_mode": "teach"})
        self.assertEqual(202, created.status_code, created.get_json())
        job_id = created.get_json()["job_id"]
        job = self.wait_for(lambda: (value if (value := self.job(job_id))["status"]
                                    in {"waiting_input", "failed"} else None))
        self.assertEqual("waiting_input", job["status"], job)
        return job_id, job

    def answer(self, job_id, question, *, answer="底边为 6 cm，对应高为 4 cm。", headers=None, **overrides):
        return self.client.post(f"/api/agent/jobs/{job_id}/clarifications/{question['request_id']}",
            headers=headers or self.headers(), json={"task_id": job_id,
            "input_version": question["input_version"], "answer": answer, **overrides})

    def test_answer_versions_conditions_and_continues_same_job_once(self):
        job_id, before = self.waiting()
        identity = before["result"]["faithful"]
        question = identity["clarification"]
        self.assertEqual(job_id, question["task_id"])
        self.assertEqual(1, question["input_version"])
        self.assertIn("底边", question["question"])
        self.assertEqual(["cancel", "answer_clarification"], identity["allowed_actions"])
        self.assertEqual(409, self.client.post(f"/api/agent/jobs/{job_id}/resume",
            json={}, headers=self.headers()).status_code)
        self.assertEqual(1, len(self.outbound))

        def solve(context):
            self.assertEqual(2, context["problem_spec"]["specification_version"])
            self.assertIn("底边为 6 cm，对应高为 4 cm。", context["problem_spec"]["assumptions"][-1])
            return {"assessment": "SOLVED", "worked": [], "failed": [], "candidates": [],
                    "solution_candidate": "面积为 12 cm²"}

        self.replies.extend([solve, {"solution_candidate": "面积 = 6 × 4 / 2 = 12 cm²。"}, ACCEPT])
        headers = self.headers()
        accepted = self.answer(job_id, question, headers=headers)
        self.assertEqual(202, accepted.status_code, accepted.get_json())
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"], final)
        self.assertEqual(2, final["result"]["faithful"]["input_version"])
        self.assertEqual(2, final["result"]["solver"]["specification_version"])
        self.assertEqual(identity["capability_snapshot"], final["result"]["faithful"]["capability_snapshot"])
        self.assertEqual(before["result"]["budget"]["deadline_at"], final["result"]["budget"]["deadline_at"])
        self.assertEqual(before["result"]["budget"]["limits"], final["result"]["budget"]["limits"])
        self.assertEqual(200, self.answer(job_id, question, headers=headers).status_code)
        self.assertEqual(409, self.answer(job_id, question, answer="改为 100", headers=headers).status_code)
        self.assertIn("12", self.report(job_id)["answer"])
        self.assertEqual(4, len(self.outbound))
        self.assertEqual(final["result"]["faithful"], self.job(job_id)["result"]["faithful"])

    def test_stale_answer_rejected_and_expiry_saves_without_dispatch(self):
        job_id, before = self.waiting()
        question = before["result"]["faithful"]["clarification"]
        for changes in ({"input_version": 0}, {"task_id": "another-task"}, {"input_version": True}):
            self.assertEqual(409, self.answer(job_id, question, **changes).status_code)
        bad = {**question, "request_id": "old-request"}
        self.assertEqual(409, self.answer(job_id, bad).status_code)
        service = self.app.extensions["showcase_workspace_service"]
        # Restart recovery is observational for a durable necessary question.
        service.store.recover_incomplete_jobs(service.checkpointer)
        self.assertEqual("waiting_input", self.job(job_id)["status"])
        with service.store._lock:
            service.store._connection.execute("UPDATE run_budgets SET ledger_json=json_set(ledger_json, '$.deadline_at', 0) WHERE run_id=?", (job_id,))
            service.store._connection.commit()
        headers = self.headers()
        saved = self.answer(job_id, question, headers=headers)
        self.assertEqual(409, saved.status_code, saved.get_json())
        self.assertEqual("new_task_required", saved.get_json()["continuation"])
        restored = self.job(job_id)["result"]["faithful"]
        self.assertEqual("expired", restored["clarification"]["status"])
        self.assertEqual("底边为 6 cm，对应高为 4 cm。", restored["clarification"]["answer"])
        self.assertEqual(["create_new_task"], restored["allowed_actions"])
        self.assertEqual(409, self.answer(job_id, question, headers=headers).status_code)
        self.assertEqual(409, self.answer(job_id, question, answer="冲突回答").status_code)
        self.assertEqual(1, len(self.outbound))
        with patch.object(service, "_submit"):
            new_headers = self.headers()
            created = self.client.post(f"/api/agent/jobs/{job_id}/clarifications/{question['request_id']}/new-task",
                                       json={}, headers=new_headers)
            self.assertEqual(202, created.status_code, created.get_json())
            new_id = created.get_json()["job_id"]
            linked = self.job(new_id)["result"]["faithful"]["clarification_source"]
            self.assertEqual(job_id, linked["task_id"])
            self.assertEqual(200, self.client.post(
                f"/api/agent/jobs/{job_id}/clarifications/{question['request_id']}/new-task",
                json={}, headers=new_headers).status_code)
        self.assertEqual(1, len(self.outbound))

    def test_answer_invalidates_prior_candidate_dependencies_and_presentation(self):
        job_id, before = self.waiting()
        question = before["result"]["faithful"]["clarification"]
        service = self.app.extensions["showcase_workspace_service"]
        # Seed a stale public-result counterexample at the persistence boundary.
        # The assertions below observe only public Job/Report contracts.
        with service.store._lock:
            connection = service.store._connection
            state = json.loads(connection.execute("SELECT state_json FROM solver_states WHERE run_id=?", (job_id,)).fetchone()[0])
            state.update(final_response="旧错误面积 999", candidate_registry=[{
                "candidate_id": "stale", "version": 1, "answer_text": "旧错误面积 999",
                "source_phase": "EXPLORE", "plan_version": 0, "attempt_index": 0,
                "review_state": "reviewed", "selection_eligible": True,
                "source_event_refs": [], "dependency_refs": [], "invalidated_by": [],
            }], verified_results_ledger=[{
                "result_id": "old-area", "source": "area", "statement": "面积 999",
                "dependencies": ["area"], "label": "verified"}])
            connection.execute("UPDATE solver_states SET state_json=? WHERE run_id=?", (json.dumps(state), job_id))
            result = json.loads(connection.execute("SELECT result_json FROM workspace_jobs WHERE job_id=?", (job_id,)).fetchone()[0])
            result["final_response"] = "旧错误面积 999"
            connection.execute("UPDATE workspace_jobs SET result_json=? WHERE job_id=?", (json.dumps(result), job_id))
            connection.commit()
        old = self.client.post(f"/api/agent/jobs/{job_id}/teach", json={}, headers=self.headers())
        self.assertEqual(200, old.status_code, old.get_json())
        with patch.object(service, "_submit"):
            response = self.answer(job_id, question)
        self.assertEqual(202, response.status_code, response.get_json())
        projected = self.job(job_id)
        self.assertEqual("", projected["result"]["final_response"])
        candidate = projected["result"]["solver"]["candidate_history"][-1]
        self.assertEqual("invalidated", candidate["review_state"])
        self.assertFalse(candidate["selection_eligible"])
        self.assertNotIn("999", self.report(job_id)["answer"])
        presentation = self.client.post(f"/api/agent/jobs/{job_id}/teach", json={}, headers=self.headers())
        self.assertEqual(200, presentation.status_code, presentation.get_json())
        history = presentation.get_json()["presentation_history"]
        self.assertTrue(history)
        self.assertTrue(all(item["status"] == "needs_review" for item in history))
