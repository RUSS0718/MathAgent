"""Changed input owns a new public task while old requests settle in place."""

import json
import threading
import unittest
from unittest.mock import patch

import requests

from tests import test_faithful_service_job as service_tests
from tests.star_product_support import ACCEPT, POLISH, SOLVED, StarJobFixture
from tests.test_faithful_s03_job import SPEC


class TaskRevisionTest(StarJobFixture, unittest.TestCase):
    open_faithful = service_tests.FaithfulServiceJobTest.open_faithful

    def revise(self, job_id, headers=None, message="计算 2+3", version=1):
        return self.client.post(f"/api/agent/jobs/{job_id}/revisions",
            headers=headers or self.headers(), json={"input_version": version, "message": message})

    def test_generated_formal_target_is_not_inherited_by_changed_problem(self):
        self.open_faithful([SPEC, SOLVED, POLISH, ACCEPT])
        old = self.client.post("/api/agent/jobs", headers=self.headers(),
            json={"session_id": self.session, "message": "1+1"}).get_json()["job_id"]
        self.terminal(old)
        service = self.app.extensions["showcase_workspace_service"]
        service.worker_enabled = False
        with service.store._lock, service.store._connection:
            identity = service.store.job_identity(old)
            identity["formal_policy"] = {"enabled": True, "source": {
                "generation_call_id": "old-intake"}, "target": {"lhs": "x+x", "rhs": "2*x"}}
            service.store._connection.execute("UPDATE workspace_jobs SET result_json=? WHERE job_id=?",
                (json.dumps(identity), old))
        revised = self.revise(old)
        self.assertEqual(202, revised.status_code, revised.get_json())
        self.assertNotIn("formal_policy", self.job(revised.get_json()["job_id"])["result"])

    def test_late_committed_settlement_wakes_queued_revision_after_workers_exit(self):
        self.open_faithful([{**SPEC, "original_problem": "计算 2+3"},
            {**SOLVED, "solution_candidate": "5"}, {**POLISH, "solution_candidate": "2+3=5"}, ACCEPT])
        from showcase.request_transport import response_events as real_events

        callbacks = []

        def transport(url, *, on_late_response, **kwargs):
            if len(callbacks) < 2:
                callbacks.append(on_late_response)
                raise requests.ReadTimeout("late response pending")
            yield from real_events(url, on_late_response=on_late_response, **kwargs)

        with patch("showcase.request_transport.response_events", side_effect=transport):
            old_ids = []
            for _ in range(2):
                old = self.client.post("/api/agent/jobs", headers=self.headers(),
                    json={"session_id": self.session, "message": "1+1"}).get_json()["job_id"]
                self.assertEqual("failed", self.terminal(old)["status"])
                old_ids.append(old)
                if len(old_ids) == 1:
                    self.session = self.client.post("/api/new_chat", headers=self.headers()).get_json()["new_session_id"]
            new = self.revise(old_ids[-1]).get_json()["job_id"]
            service = self.app.extensions["showcase_workspace_service"]
            # Both executor threads must reach the barrier: no old worker remains to wake the queue.
            barrier = threading.Barrier(3, timeout=5)
            workers = [service._executor.submit(barrier.wait) for _ in range(2)]
            barrier.wait()
            for worker in workers:
                worker.result(timeout=5)
            self.assertEqual("queued", self.job(new)["status"])
            self.assertEqual(0, len(self.outbound))
            reply = requests.Response()
            reply.status_code = 200
            body = json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": "2"}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}).encode()
            callbacks[0](reply, body, .01, .2, True)
            self.assertEqual("succeeded", self.terminal(new)["status"])
            self.assertIn("5", self.report(new)["answer"])
            self.assertEqual(4, len(self.outbound))
            self.assertEqual("failed", self.job(old_ids[0])["status"])
            self.assertEqual(0, self.job(old_ids[0])["result"]["budget"]["unresolved_attempts"])
            self.assertEqual(1, self.job(old_ids[1])["result"]["budget"]["unresolved_attempts"])

    def test_revision_fences_old_dispatch_and_late_result_without_crosswrite(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def late_intake(context):
            entered.set()
            self.assertTrue(release.wait(5))
            return SPEC

        self.open_faithful([late_intake])
        old = self.client.post("/api/agent/jobs", headers=self.headers(),
            json={"session_id": self.session, "message": "1+1"}).get_json()["job_id"]
        self.assertTrue(entered.wait(5))
        before = self.job(old)["result"]["budget"]
        service = self.app.extensions["showcase_workspace_service"]
        # Keep the new task queued so its independent evidence is observable.
        service.worker_enabled = False
        headers = self.headers()
        response = self.revise(old, headers)
        self.assertEqual(202, response.status_code, response.get_json())
        new = response.get_json()["job_id"]
        self.assertNotEqual(old, new)
        canceled = self.job(old)
        self.assertEqual("canceled", canceled["status"])
        self.assertEqual(before["reserved_tokens"], canceled["result"]["budget"]["reserved_tokens"])
        self.assertEqual(new, canceled["result"]["faithful"]["revision_to"]["task_id"])
        created = self.job(new)
        self.assertEqual(old, created["result"]["faithful"]["revision_source"]["task_id"])
        self.assertFalse(created["result"].get("final_response"))
        self.assertFalse(created["result"].get("verification"))
        for repeated in (headers, self.headers()):
            replay = self.revise(old, repeated)
            self.assertEqual(200, replay.status_code, replay.get_json())
            self.assertEqual(new, replay.get_json()["job_id"])
            receipt = self.client.get(f"/api/agent/submissions/{repeated['Idempotency-Key']}")
            self.assertEqual(200, receipt.status_code, receipt.get_json())
            self.assertEqual(new, receipt.get_json()["job_id"])
            self.assertEqual(409, self.revise(old, repeated, message="别的题").status_code)
        self.assertEqual(409, self.revise(old, headers, message="别的题").status_code)
        self.assertEqual(409, self.revise(old, version=2).status_code)
        release.set()
        self.wait_for(lambda: self.job(old)["result"]["budget"]["unresolved_attempts"] == 0)
        new_spec = {**SPEC, "original_problem": "计算 2+3"}
        self.replies.extend([new_spec, {**SOLVED, "solution_candidate": "5"},
                             {**POLISH, "solution_candidate": "2+3=5"}, ACCEPT])
        service._execute(new)
        final = self.terminal(new)
        self.assertEqual("succeeded", final["status"], final)
        self.assertIn("5", self.report(new)["answer"])
        self.assertEqual("canceled", self.job(old)["status"])
        self.assertFalse(self.job(old)["result"].get("final_response"))
        self.assertEqual(5, len(self.outbound))

    def test_unknown_reservation_survives_revision_and_does_not_transfer_evidence(self):
        self.open_faithful([requests.ReadTimeout("unknown")])
        old = self.client.post("/api/agent/jobs", headers=self.headers(),
            json={"session_id": self.session, "message": "1+1"}).get_json()["job_id"]
        before = self.terminal(old)
        service = self.app.extensions["showcase_workspace_service"]
        service.worker_enabled = False
        response = self.revise(old)
        self.assertEqual(202, response.status_code, response.get_json())
        new = response.get_json()["job_id"]
        after = self.job(old)
        self.assertEqual(before["result"]["budget"], after["result"]["budget"])
        self.assertEqual(before["result"]["solver"]["recovery"], after["result"]["solver"]["recovery"])
        self.assertEqual([], after["result"]["faithful"]["allowed_actions"])
        self.assertEqual(409, self.client.post(f"/api/agent/jobs/{old}/resume",
                                             json={}, headers=self.headers()).status_code)
        self.assertFalse(self.job(new)["result"].get("solver"))
        self.assertEqual(1, len(self.outbound))

    def test_capacity_uses_worker_limit_and_ignores_known_rejected_request(self):
        rejected = requests.Response()
        rejected.status_code = 400
        self.open_faithful([requests.HTTPError(response=rejected), requests.ReadTimeout("unknown")])
        first = self.client.post("/api/agent/jobs", headers=self.headers(),
            json={"session_id": self.session, "message": "1+1"}).get_json()["job_id"]
        self.terminal(first)
        self.session = self.client.post("/api/new_chat", headers=self.headers()).get_json()["new_session_id"]
        old = self.client.post("/api/agent/jobs", headers=self.headers(),
            json={"session_id": self.session, "message": "1+1"}).get_json()["job_id"]
        self.terminal(old)
        service = self.app.extensions["showcase_workspace_service"]
        service.worker_enabled = False
        new = self.revise(old).get_json()["job_id"]
        service.worker_capacity = 1
        service._execute(new)
        self.assertEqual("queued", self.job(new)["status"])
        self.assertEqual(2, len(self.outbound))
        service.worker_capacity = 2
        self.replies.extend([{**SPEC, "original_problem": "计算 2+3"},
            {**SOLVED, "solution_candidate": "5"}, {**POLISH, "solution_candidate": "2+3=5"}, ACCEPT])
        service._execute(new)
        self.assertEqual("succeeded", self.terminal(new)["status"])
        self.assertEqual(6, len(self.outbound))
