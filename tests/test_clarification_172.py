"""Necessary clarification is consumed through the authenticated public Job API."""

import json
import unittest
import uuid
from copy import deepcopy
from unittest.mock import patch

import requests

from showcase.formal_specification import canonical_identity
from tests import test_faithful_service_job as service_tests
from tests.star_product_support import ACCEPT, StarJobFixture
from tests.test_faithful_s09_public_job import SPEC as RATIONAL_SPEC
from tests.test_faithful_s09_public_job import TARGET

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


ANSWER = "底边为 6 cm，对应高为 4 cm。"
SOLVED_AREA = {"assessment": "SOLVED", "worked": [], "failed": [],
               "candidates": [], "solution_candidate": "面积为 12 cm²"}
POLISHED_AREA = {"solution_candidate": "面积 = 6 × 4 / 2 = 12 cm²。"}
REASSESSED = {key: value for key, value in SPEC.items() if key != "clarification"} | {
    "applicable_condition": ANSWER,
}


class ClarificationTest(StarJobFixture, unittest.TestCase):
    open_faithful = service_tests.FaithfulServiceJobTest.open_faithful

    def open_star(self, replies, **config):
        super().open_star(replies, SHOWCASE_PRESENTATION_ENABLED=True, **config)

    def waiting(self, *replies):
        self.open_faithful(list(replies) or [SPEC])
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
            return SOLVED_AREA

        def assess(context):
            self.assertEqual(PROBLEM, context["original_problem"])
            self.assertEqual(ANSWER, context["clarification_input"]["answer"])
            self.assertEqual(question["question"], context["clarification_input"]["question"])
            return REASSESSED

        self.replies.extend([assess, solve, POLISHED_AREA, ACCEPT])
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
        self.assertEqual(5, len(self.outbound))
        self.assertEqual(final["result"]["faithful"], self.job(job_id)["result"]["faithful"])

    def test_clarification_rebinds_formal_selection_to_effective_spec(self):
        initial = deepcopy(RATIONAL_SPEC)
        initial["clarification"] = {"question": "Is x positive?", "reason": "Confirm the additional condition."}
        initial["formalization"] = {"status": "not_selected", "reason": "awaiting clarification",
                                    "require_formal": False, "obligation_ids": [], "target": None}
        reply = deepcopy(RATIONAL_SPEC)
        reply["applicable_condition"] = "x > 0"
        reply["formalization"] = {
            "status": "proposed", "reason": "rational identity", "require_formal": True,
            "obligation_ids": ["root:identity"],
            "target": {key: value for key, value in TARGET.items()
                       if key not in {"hash", "_lean_lhs", "_lean_rhs"}},
        }
        self.open_faithful([initial, reply, SOLVED_AREA, POLISHED_AREA, ACCEPT])
        created = self.client.post("/api/agent/jobs", headers=self.headers(),
            json={"session_id": self.session, "message": initial["original_problem"]})
        self.assertEqual(202, created.status_code, created.get_json())
        job_id = created.get_json()["job_id"]
        before = self.wait_for(lambda: value if (value := self.job(job_id))["status"]
                               in {"waiting_input", "failed"} else None)
        self.assertEqual("waiting_input", before["status"], before)
        question = before["result"]["faithful"]["clarification"]
        self.assertEqual(202, self.answer(job_id, question, answer="x > 0").status_code)
        final = self.terminal(job_id)
        service = self.app.extensions["showcase_workspace_service"]
        with service.store._lock:
            state = json.loads(service.store._connection.execute(
                "SELECT state_json FROM solver_states WHERE run_id=?", (job_id,)).fetchone()[0])
        selection = state["formalization"]
        self.assertTrue(selection["require_formal"])
        self.assertEqual("unsupported", selection["status"])
        self.assertEqual("spec_target_mismatch", selection["reason"])
        self.assertNotIn("target", selection)
        self.assertEqual(2, state["problem_spec"]["specification_version"])
        self.assertIn("x > 0", state["problem_spec"]["assumptions"][-1])
        self.assertEqual(canonical_identity(state["problem_spec"]), selection["source"]["specification_hash"])
        self.assertEqual(f"{job_id}:problem-intake:2", selection["source"]["generation_call_id"])
        self.assertEqual(["root:identity"], selection["source"]["obligation_ids"])
        self.assertEqual("failed", final["status"])
        self.assertEqual("unsupported", final["result"]["formal_verification"]["status"])
        self.assertEqual("unmet", final["result"]["formal_verification"]["assessment"]["status"])
        self.assertEqual(5, len(self.outbound))
        self.assertEqual(before["result"]["budget"]["deadline_at"], final["result"]["budget"]["deadline_at"])

    def test_live_reply_shapes_require_one_budgeted_repair_before_solving(self):
        generic = "三角形的几何参数已明确给出，可直接计算其数值面积。"
        base = {key: value for key, value in REASSESSED.items() if key != "applicable_condition"}
        shapes = (
            {"clarification": {"question": "", "reason": ""}, "applicable_condition": generic},
            {"clarification": None, "applicable_condition": generic},
            {"clarification": None, "applicable_condition": None},
            {},
        )
        with self.subTest(initial="empty root obligations"):
            def repair_empty_roots(context):
                self.assertIn("repair_instruction", context)
                return SPEC

            _, waiting = self.waiting(
                {**SPEC, "root_obligations": [], "applicable_condition": None},
                repair_empty_roots,
            )
            self.assertEqual(["problem_intake", "problem_intake"],
                             [request["role"] for request in self.outbound])
            self.assertEqual(2, waiting["result"]["budget"]["logical_calls"])
            self.assertEqual(SPEC["clarification"]["question"],
                             waiting["result"]["faithful"]["clarification"]["question"])

        for index, shape in enumerate(shapes):
            with self.subTest(shape=shape):
                def repair_initial(context):
                    self.assertIn("repair_instruction", context)
                    self.assertNotIn("clarification_input", context)
                    return SPEC

                initial = index == 0
                job_id, before = (self.waiting({**SPEC, "applicable_condition": generic}, repair_initial)
                                  if initial else self.waiting())
                self.assertEqual(2 if initial else 1, len(self.outbound))
                question = before["result"]["faithful"]["clarification"]

                def repair(context):
                    self.assertIn("repair_instruction", context)
                    self.assertEqual(ANSWER, context["clarification_input"]["answer"])
                    return {**REASSESSED, "clarification": None} if initial else REASSESSED

                def solve(context):
                    self.assertIn(ANSWER, context["problem_spec"]["assumptions"][-1])
                    return SOLVED_AREA

                self.replies.extend([{**base, **shape}, repair, solve, POLISHED_AREA, ACCEPT])
                self.assertEqual(202, self.answer(job_id, question).status_code)
                final = self.wait_for(lambda: value if (value := self.job(job_id))["status"]
                                      in {"succeeded", "failed", "waiting_input"} else None)
                self.assertEqual("succeeded", final["status"],
                                 final["result"]["solver"].get("result_reason"))
                self.assertEqual(["problem_intake"] * (4 if initial else 3) + ["explore", "explore_polish",
                                                           "whole_solution_verifier"],
                                 [request["role"] for request in self.outbound])
                self.assertEqual(7 if initial else 6, final["result"]["budget"]["logical_calls"])
                self.assertEqual(before["result"]["budget"]["deadline_at"],
                                 final["result"]["budget"]["deadline_at"])

    def test_non_answer_reopens_versioned_question_without_solving(self):
        job_id, before = self.waiting()
        question = before["result"]["faithful"]["clarification"]
        self.replies.append(SPEC)
        headers = self.headers()
        self.assertEqual(202, self.answer(job_id, question, answer="我不知道高。", headers=headers).status_code)
        latest = self.wait_for(lambda: value if (value := self.job(job_id))["status"]
                               in {"waiting_input", "failed", "succeeded"} else None)
        self.assertEqual("waiting_input", latest["status"], latest)
        faithful = latest["result"]["faithful"]
        followup = faithful["clarification"]
        self.assertEqual(job_id, followup["task_id"])
        self.assertEqual(2, followup["input_version"])
        self.assertNotEqual(question["request_id"], followup["request_id"])
        self.assertEqual(1, faithful["specification_version"])
        self.assertEqual(["cancel", "answer_clarification"], faithful["allowed_actions"])
        self.assertEqual(200, self.answer(job_id, question, answer="我不知道高。", headers=headers).status_code)
        self.assertEqual(409, self.answer(job_id, question).status_code)
        self.assertEqual(before["result"]["budget"]["deadline_at"], latest["result"]["budget"]["deadline_at"])
        self.assertEqual(2, len(self.outbound))
        self.replies.extend([REASSESSED, SOLVED_AREA, POLISHED_AREA, ACCEPT])
        self.assertEqual(202, self.answer(job_id, followup).status_code)
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"])
        self.assertEqual(3, final["result"]["faithful"]["input_version"])
        self.assertEqual(2, final["result"]["faithful"]["specification_version"])
        self.assertEqual(6, len(self.outbound))

    def test_unknown_clarification_requires_explicit_retry_on_same_run(self):
        job_id, before = self.waiting()
        question = before["result"]["faithful"]["clarification"]
        self.replies.extend([requests.ReadTimeout("clarification outcome unknown"), SPEC])
        self.assertEqual(202, self.answer(job_id, question).status_code)
        failed = self.terminal(job_id)
        faithful = failed["result"]["faithful"]
        self.assertEqual("evaluating", faithful["clarification"]["status"])
        self.assertEqual(1, faithful["specification_version"])
        self.assertEqual(["retry_unknown_call"], faithful["allowed_actions"])
        recovery = failed["result"]["solver"]["recovery"]
        self.assertEqual("problem_intake", recovery["unknown_calls"][0]["role"])
        resume = f"/api/agent/jobs/{job_id}/resume"
        self.assertEqual(409, self.client.post(resume, json={}, headers=self.headers()).status_code)
        self.assertEqual(2, len(self.outbound))
        response = self.client.post(resume, headers=self.headers(), json={"retry_call": {
            "call_id": recovery["unknown_calls"][0]["call_id"], "new_call_id": str(uuid.uuid4())}})
        self.assertEqual(202, response.status_code, response.get_json())
        latest = self.wait_for(lambda: value if (value := self.job(job_id))["status"] == "waiting_input" else None)
        self.assertEqual(3, len(self.outbound))
        self.assertEqual(ANSWER, self.outbound[-1]["clarification_input"]["answer"])
        self.assertEqual(before["result"]["budget"]["deadline_at"], latest["result"]["budget"]["deadline_at"])
        self.assertEqual(1, latest["result"]["budget"]["unknown_attempts"])

    def test_deadline_after_queue_keeps_answer_and_linked_task(self):
        job_id, before = self.waiting()
        question = before["result"]["faithful"]["clarification"]
        service = self.app.extensions["showcase_workspace_service"]
        with patch.object(service, "_submit"):
            headers = self.headers()
            self.assertEqual(202, self.answer(job_id, question, headers=headers).status_code)
            with service.store._lock, service.store._connection as connection:
                connection.execute("UPDATE run_budgets SET ledger_json=json_set(ledger_json, '$.deadline_at', 0) WHERE run_id=?", (job_id,))
            service._execute(job_id)
            faithful = self.job(job_id)["result"]["faithful"]
            self.assertEqual("expired", faithful["clarification"]["status"])
            self.assertEqual("底边为 6 cm，对应高为 4 cm。", faithful["clarification"]["answer"])
            self.assertEqual(["create_new_task"], faithful["allowed_actions"])
            replay = self.answer(job_id, question, headers=headers)
            self.assertEqual(200, replay.status_code, replay.get_json())
            self.assertEqual("same_task", replay.get_json()["continuation"])
            expired = self.answer(job_id, question)
            self.assertEqual(409, expired.status_code, expired.get_json())
            self.assertEqual("clarification_expired", expired.get_json()["code"])
            self.assertEqual("new_task_required", expired.get_json()["continuation"])
            self.assertTrue(expired.get_json()["answer_saved"])
            response = self.client.post(f"/api/agent/jobs/{job_id}/clarifications/{question['request_id']}/new-task",
                                        json={}, headers=self.headers())
            self.assertEqual(202, response.status_code, response.get_json())
            self.assertEqual(job_id, self.job(response.get_json()["job_id"])["result"]["faithful"]["clarification_source"]["task_id"])
        self.assertEqual(1, len(self.outbound))

    def test_public_run_strips_raw_reply_from_existing_snapshot(self):
        job_id, before = self.waiting()
        question = before["result"]["faithful"]["clarification"]
        store = self.app.extensions["showcase_workspace_service"].store
        with store._lock, store._connection as connection:
            # Reproduce the snapshot shape written by 0649be6 before sanitization.
            reply = {**question, "status": "expired", "answer": "legacy-raw-reply-sentinel",
                     "receipt": {"answer_saved": True}}
            connection.execute(
                "UPDATE runs SET snapshot_json=json_set(snapshot_json, "
                "'$.result.faithful.clarification_reply', json(?)) WHERE run_id=?",
                (json.dumps(reply), job_id),
            )
        run = self.client.get(f"/api/runs/{job_id}")
        self.assertEqual(200, run.status_code)
        self.assertNotIn("legacy-raw-reply-sentinel", run.get_data(as_text=True))
        identity = run.get_json()["result"]["faithful"]
        self.assertNotIn("clarification_reply", identity)
        self.assertEqual({**question, "status": "expired"}, identity["clarification"])

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
        secret_answer = f"{ANSWER} token=private-clarification-secret"
        saved = self.answer(job_id, question, headers=headers, answer=secret_answer)
        self.assertEqual(409, saved.status_code, saved.get_json())
        self.assertEqual("new_task_required", saved.get_json()["continuation"])
        restored = self.job(job_id)["result"]["faithful"]
        self.assertEqual("expired", restored["clarification"]["status"])
        self.assertNotIn("private-clarification-secret", restored["clarification"]["answer"])
        run = self.client.get(f"/api/runs/{job_id}")
        self.assertEqual(200, run.status_code, run.get_json())
        self.assertNotIn("private-clarification-secret", run.get_data(as_text=True))
        run_question = run.get_json()["result"]["faithful"]["clarification"]
        self.assertEqual("expired", run_question["status"])
        self.assertNotIn("answer", run_question)
        self.assertNotIn("receipt", run_question)
        self.assertNotIn("clarification_reply", run.get_json()["result"]["faithful"])
        self.assertEqual(["create_new_task"], restored["allowed_actions"])
        self.assertEqual(409, self.answer(job_id, question, headers=headers, answer=secret_answer).status_code)
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
        self.replies.extend([REASSESSED, SOLVED_AREA, POLISHED_AREA, ACCEPT])
        with patch.object(service, "_submit"):
            response = self.answer(job_id, question)
            self.assertEqual(202, response.status_code, response.get_json())
            self.assertEqual("", self.job(job_id)["result"]["final_response"])
            service.store.recover_incomplete_jobs(service.checkpointer)
        self.assertIn("resume", self.job(job_id)["result"]["faithful"]["allowed_actions"])
        resumed = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={}, headers=self.headers())
        self.assertEqual(202, resumed.status_code, resumed.get_json())
        projected = self.terminal(job_id)
        self.assertEqual("succeeded", projected["status"])
        candidate = [item for item in projected["result"]["solver"]["candidate_history"]
                     if item["answer_text"] == "旧错误面积 999"][-1]
        self.assertEqual("invalidated", candidate["review_state"])
        self.assertFalse(candidate["selection_eligible"])
        self.assertNotIn("999", self.report(job_id)["answer"])
        presentation = self.client.post(f"/api/agent/jobs/{job_id}/teach", json={}, headers=self.headers())
        self.assertEqual(200, presentation.status_code, presentation.get_json())
        history = presentation.get_json()["presentation_history"]
        self.assertTrue(history)
        self.assertTrue(any(item["status"] == "needs_review" for item in history))
