"""Submission recovery through the authenticated public API."""
import unittest
import uuid
from tests import test_workspace_jobs as workspace_tests


class SubmissionRecoveryTest(unittest.TestCase):
    setUp = workspace_tests.WorkspaceJobsContractTest.setUp
    tearDown = workspace_tests.WorkspaceJobsContractTest.tearDown
    _headers = workspace_tests.WorkspaceJobsContractTest._headers

    def test_lost_response_lookup_is_read_only_and_payload_conflicts(self):
        session = self.client.post("/api/new_chat", headers=self._headers()).get_json()["new_session_id"]
        key = str(uuid.uuid4())
        headers = self._headers(**{"Idempotency-Key": key})
        payload = {"session_id": session, "message": "2+3"}
        accepted = self.client.post("/api/agent/jobs", json=payload, headers=headers).get_json()
        for _ in range(2):
            found = self.client.get(f"/api/agent/submissions/{key}")
            self.assertEqual(200, found.status_code)
            self.assertEqual(accepted["job_id"], found.get_json()["job_id"])
        replay = self.client.post("/api/agent/jobs", json=payload, headers=headers)
        self.assertTrue(replay.get_json()["existing"])
        conflict = self.client.post("/api/agent/jobs", json={**payload, "message": "2+4"}, headers=headers)
        self.assertEqual(409, conflict.status_code)
        self.assertEqual("idempotency_conflict", conflict.get_json()["code"])
        self.assertEqual(404, self.client.get(f"/api/agent/submissions/{uuid.uuid4()}").status_code)
