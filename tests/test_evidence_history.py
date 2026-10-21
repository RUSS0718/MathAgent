"""Append checks preserve public artifacts across persistent workspace reopen."""
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

import test_workspace_jobs as workspace_contracts

from showcase.flask_app import create_app


class EvidenceHistoryContractTest(unittest.TestCase):
    setUp = workspace_contracts.WorkspaceJobsContractTest.setUp
    def tearDown(self):
        if hasattr(self, "second_app"):
            for name in ("showcase_workspace_service", "showcase_run_service", "loopback_store"):
                self.second_app.extensions[name].close()
        workspace_contracts.WorkspaceJobsContractTest.tearDown(self)
    _headers = workspace_contracts.WorkspaceJobsContractTest._headers

    def test_append_checks_preserve_answer_and_history_across_reopen(self):
        session = self.client.post("/api/new_chat", headers=self._headers()).get_json()["new_session_id"]
        job_id = self.client.post("/api/agent/jobs", json={"message": "x-1=0", "session_id": session}, headers=self._headers(**{"Idempotency-Key": "00000000-0000-4000-8000-000000000024"})).get_json()["job_id"]
        for _ in range(200):
            job = self.client.get(f"/api/agent/jobs/{job_id}").get_json()
            if job["status"] == "succeeded":
                break
            time.sleep(0.01)
        original = job["result"]
        self.assertEqual("unknown", original["verification"]["status"])
        self.assertTrue(original["verification"]["artifact"]["sha256"])
        self.assertEqual(original["verification"], self.client.get(f"/api/runs/{job_id}").get_json()["result"]["verification"])
        self.assertEqual(original["verification"], self.client.get(f"/api/runs/{job_id}/evidence").get_json()["verification"])
        original_events = self.client.get(f"/api/runs/{job_id}/events").get_json()["events"]
        payload = {"schema_version": 1, "variable": "x", "coefficients": ["1", "-1"], "domain": {"kind": "real"}, "candidates": ["1"]}
        self.second_app = second_app = create_app({"TESTING": True, "SHOWCASE_DATA_DIR": str(self.root)})
        self.addCleanup(second_app.extensions["loopback_store"].close)
        self.addCleanup(second_app.extensions["showcase_run_service"].close)
        self.addCleanup(second_app.extensions["showcase_workspace_service"].close)
        def append(index):
            with (self.app if index == 0 else second_app).test_client() as client:
                csrf = client.get("/api/check_auth").get_json()["csrf_token"]
                return client.post(f"/api/agent/jobs/{job_id}/polynomial-check", json=payload, headers={"X-CSRF-Token": csrf}).status_code
        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertEqual([200, 200], list(executor.map(append, range(2))))
        current = self.client.get(f"/api/agent/jobs/{job_id}").get_json()["result"]
        for key, value in original.items():
            if key != "verification":
                self.assertEqual(value, current[key])
        check = current["verification"]
        self.assertEqual(3, len(check["history"]))
        self.assertEqual("unknown", check["status"])
        self.assertEqual("unknown", check["history"][-1]["coverage_status"])
        self.assertEqual("pass", check["history"][-1]["candidate_status"])
        self.assertEqual(original_events, self.client.get(f"/api/runs/{job_id}/events").get_json()["events"][:len(original_events)])
        before = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        self.assertEqual(check, before["verification"])
        self.assertEqual(check, self.client.get(f"/api/agent/jobs/{job_id}/report").get_json()["report"]["checks"])
        for name in ("showcase_workspace_service", "showcase_run_service", "loopback_store"):
            self.app.extensions[name].close()
        self.app = create_app({"TESTING": True, "SHOWCASE_DATA_DIR": str(self.root)})
        self.client = self.app.test_client()
        self.client.get("/api/check_auth")
        self.assertEqual(before, self.client.get(f"/api/runs/{job_id}/evidence").get_json())
        self.assertEqual(before, self.client.get(f"/api/runs/{job_id}/evidence").get_json())

    def test_running_job_rejects_append_without_creating_evidence(self):
        for name in ("showcase_workspace_service", "showcase_run_service", "loopback_store"):
            self.app.extensions[name].close()
        self.app = create_app({"TESTING": True, "SHOWCASE_DATA_DIR": str(self.root), "SHOWCASE_WORKER_ENABLED": False})
        self.client = self.app.test_client()
        self.csrf = self.client.get("/api/check_auth").get_json()["csrf_token"]
        session = self.client.post("/api/new_chat", headers=self._headers()).get_json()["new_session_id"]
        job_id = self.client.post("/api/agent/jobs", json={"message": "x-1=0", "session_id": session}, headers=self._headers(**{"Idempotency-Key": "00000000-0000-4000-8000-000000000025"})).get_json()["job_id"]
        before = self.client.get(f"/api/runs/{job_id}/events").get_json()["events"]
        response = self.client.post(f"/api/agent/jobs/{job_id}/polynomial-check", json={}, headers=self._headers())
        self.assertEqual(409, response.status_code)
        self.assertEqual("verification_requires_terminal_job", response.get_json()["error"])
        self.assertEqual(before, self.client.get(f"/api/runs/{job_id}/events").get_json()["events"])

