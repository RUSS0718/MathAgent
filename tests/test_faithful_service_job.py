"""Ordinary text traverses authenticated Job, metered intake and answer delivery."""

import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import requests

from showcase.run_budget import RunBudgetLimits
from showcase.star_product_config import CORE_FEATURES
from tests.star_product_support import ACCEPT, POLISH, SOLVED, StarJobFixture
from tests.test_faithful_s03_job import CAPACITY_POLICY, ENDPOINT, SPEC


class FaithfulServiceJobTest(StarJobFixture, unittest.TestCase):
    def open_faithful(self, replies, *, calls=8):
        """Use the ordinary service entry with controlled HTTP and a root budget."""
        self.enterContext(patch.dict(os.environ, {"INTERN_API_BASE": ENDPOINT}))
        self.open_star(replies, SHOWCASE_FAITHFUL_AUTONOMOUS=True,
            SHOWCASE_STAR_FULL_ENABLED=True,
            SHOWCASE_STAR_FULL_FEATURES=dict.fromkeys(CORE_FEATURES | {
                "auto_problem_spec", "problem_spec", "context_pack", "proof_graph",
                "progress_scheduling", "serial_routes"}, True),
            SHOWCASE_STAR_CONTEXT_CAPACITY=CAPACITY_POLICY,
            SHOWCASE_STAR_FULL_BUDGET=RunBudgetLimits(max_model_calls=calls, max_http_attempts=calls))
        pipeline = self.app.extensions["showcase_workspace_service"].star_pipeline
        self.enterContext(patch.object(pipeline, "full_gaps", return_value=[]))

    def submit_plain(self):
        response = self.client.post("/api/agent/jobs", headers=self.headers(),
            json={"message": "1+1", "session_id": self.session})
        self.assertEqual(202, response.status_code, response.get_json())
        return response.get_json()["job_id"]

    def test_exhausted_intake_budget_has_persistent_public_reason(self):
        self.open_faithful([SPEC], calls=1)
        job_id = self.submit_plain()
        final = self.terminal(job_id)
        self.assertEqual("failed", final["status"])
        self.assertEqual("partial_budget_exhausted", final["result"]["solver"]["status"])
        faithful = final["result"]["faithful"]
        self.assertEqual("budget_exhausted", faithful["phase"])
        self.assertEqual("model_call_budget_exhausted", faithful["reason"])
        self.assertEqual([], faithful["allowed_actions"])
        self.assertEqual(faithful, self.job(job_id)["result"]["faithful"])
        self.assertEqual(1, len(self.outbound))

    def test_public_unknown_intake_retry_establishes_spec_before_solving(self):
        self.open_faithful([requests.ReadTimeout("unknown intake"), SPEC, SOLVED, POLISH, ACCEPT])
        job_id = self.submit_plain()
        first = self.terminal(job_id)
        self.assertEqual("failed", first["status"])
        before = first["result"]["budget"]
        old_id = first["result"]["solver"]["recovery"]["unknown_calls"][0]["call_id"]
        self.assertEqual(["retry_unknown_call"], first["result"]["faithful"]["allowed_actions"])
        refused = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={}, headers=self.headers())
        self.assertEqual(409, refused.status_code)
        self.assertEqual(1, len(self.outbound))
        new_id = str(uuid.uuid4())
        body = {"retry_call": {"call_id": old_id, "new_call_id": new_id}}
        headers = self.headers()
        resumed = self.client.post(f"/api/agent/jobs/{job_id}/resume", json=body, headers=headers)
        self.assertEqual(202, resumed.status_code, resumed.get_json())
        final = self.terminal(job_id)
        self.assertEqual(["problem_intake", "problem_intake", "explore", "explore_polish", "whole_solution_verifier"],
                         [item["role"] for item in self.outbound], final)
        self.assertEqual("succeeded", final["status"], final)
        solver = final["result"]["solver"]
        self.assertEqual("completed", solver["intake_status"])
        self.assertEqual(1, solver["specification_version"])
        self.assertEqual("1+1", self.outbound[2]["problem_spec"]["original_problem"])
        self.assertEqual(new_id, self.outbound[1]["call_id"])
        retry = solver["recovery"]["retries"][0]
        self.assertEqual(old_id, retry["retry_of"])
        after = final["result"]["budget"]
        self.assertEqual(before["deadline_at"], after["deadline_at"])
        self.assertEqual(before["reserved_tokens"], after["reserved_tokens"])
        self.assertEqual(1, after["unknown_attempts"])
        self.assertEqual(5, after["http_attempts"])
        self.assertEqual(200, self.client.post(f"/api/agent/jobs/{job_id}/resume",
                         json=body, headers=headers).status_code)
        self.job(job_id)
        self.assertEqual(5, len(self.outbound))

    def test_failed_committed_intake_advertises_resume_and_reuses_spec(self):
        from showcase.solver_harness.problem_intake import ensure_problem_spec

        self.open_faithful([SPEC, SOLVED, POLISH, ACCEPT])

        def fail_after_checkpoint(harness, run, problem):
            commit = harness.commit_event

            def before_accept(*args, **kwargs):
                if kwargs["event"]["type"] == "problem_intake_accepted":
                    raise RuntimeError("injected failure after committed intake response")
                return commit(*args, **kwargs)

            with patch.object(harness, "commit_event", side_effect=before_accept):
                return ensure_problem_spec(harness, run, problem)

        with patch("showcase.solver_harness.problem_intake.ensure_problem_spec",
                   side_effect=fail_after_checkpoint):
            job_id = self.submit_plain()
            first = self.terminal(job_id)
        self.assertEqual("failed", first["status"])
        self.assertEqual("pending", first["result"]["solver"]["intake_status"])
        self.assertEqual(["resume"], first["result"]["faithful"]["allowed_actions"])
        response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={}, headers=self.headers())
        self.assertEqual(202, response.status_code, response.get_json())
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"], final)
        self.assertEqual("completed", final["result"]["solver"]["intake_status"])
        self.assertEqual(1, final["result"]["solver"]["specification_version"])
        self.assertEqual(["problem_intake", "explore", "explore_polish", "whole_solution_verifier"],
                         [item["role"] for item in self.outbound])
        self.assertEqual(first["result"]["budget"]["deadline_at"], final["result"]["budget"]["deadline_at"])

    def test_expired_unknown_has_no_resume_or_retry_and_get_does_not_write(self):
        self.open_faithful([requests.ReadTimeout("unknown intake")])
        job_id = self.submit_plain()
        first = self.terminal(job_id)
        old_id = first["result"]["solver"]["recovery"]["unknown_calls"][0]["call_id"]
        store = self.app.extensions["showcase_workspace_service"].store
        # Inject an elapsed root deadline at the persistence boundary.
        with store._lock:
            store._connection.execute("UPDATE run_budgets SET ledger_json=json_set(ledger_json, '$.deadline_at', 0) WHERE run_id=?", (job_id,))
            store._connection.commit()
            before = store._connection.total_changes
        expired = self.job(job_id)
        self.assertEqual([], expired["result"]["faithful"]["allowed_actions"])
        self.job(job_id)
        self.assertEqual(before, store._connection.total_changes)
        for body in ({}, {"retry_call": {"call_id": old_id, "new_call_id": str(uuid.uuid4())}}):
            response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json=body, headers=self.headers())
            self.assertEqual(409, response.status_code, response.get_json())
        self.assertEqual(1, len(self.outbound))

    def test_loaded_service_configuration_delivers_over_its_selected_transport(self):
        from showcase.faithful_service_config import load_faithful_config
        from showcase.request_transport import INTERN_S2_LIVE_ENDPOINT

        self.enterContext(patch.dict(os.environ, {"INTERN_API_BASE": INTERN_S2_LIVE_ENDPOINT,
                                                "INTERN_MODEL": "intern-s2"}))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "service.json"
            path.write_text(json.dumps({
                "version": "faithful-service-v1", "python_image_id": "sha256:" + "a" * 64,
                "context_capacity": {**CAPACITY_POLICY, "endpoint": INTERN_S2_LIVE_ENDPOINT,
                                     "output_reserve_tokens": 32768},
                "budget": {"max_model_calls": 8, "max_http_attempts": 8, "max_tool_calls": 1,
                           "max_tokens": 262144, "max_runtime_seconds": 180},
            }), encoding="utf-8")
            config = load_faithful_config(path)
        from showcase.stream_preference import VERIFIED_STREAM_PROFILES

        # Keep the production profile and replace only HTTP; the generic fixture's
        # synthetic profiles do not cover every ContextPack message shape.
        with patch("tests.controlled_stream_profiles.configure_controlled_streaming",
                   return_value=VERIFIED_STREAM_PROFILES):
            self.open_star([SPEC, SOLVED, POLISH, ACCEPT], **config)
        pipeline = self.app.extensions["showcase_workspace_service"].star_pipeline
        with patch.object(pipeline, "full_gaps", return_value=[]):
            created = self.client.post("/api/agent/jobs", headers=self.headers(),
                                       json={"message": "1+1", "session_id": self.session})
            self.assertEqual(202, created.status_code, created.get_json())
            terminal = self.terminal(created.get_json()["job_id"])
        self.assertEqual("succeeded", terminal["status"], terminal)
        self.assertEqual(4, len(self.outbound))
        self.assertEqual(4, terminal["result"]["budget"]["http_attempts"])

    def test_plain_text_default_route_delivers_and_reloads_without_duplicate_calls(self):
        self.enterContext(patch.dict(os.environ, {"INTERN_API_BASE": ENDPOINT}))
        self.open_star([SPEC, SOLVED, POLISH, ACCEPT],
            SHOWCASE_FAITHFUL_AUTONOMOUS=True,
            SHOWCASE_STAR_FULL_ENABLED=True,
            SHOWCASE_STAR_FULL_FEATURES=dict.fromkeys(CORE_FEATURES | {
                "auto_problem_spec", "problem_spec", "context_pack", "proof_graph",
                "progress_scheduling", "serial_routes"}, True),
            SHOWCASE_STAR_CONTEXT_CAPACITY=CAPACITY_POLICY,
            SHOWCASE_STAR_FULL_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8),
        )
        pipeline = self.app.extensions["showcase_workspace_service"].star_pipeline
        # This contract covers execution with a controlled provider. Isolation
        # readiness has separate tests; this fixture never claims live readiness.
        with patch.object(pipeline, "full_gaps", return_value=[]):
            headers = self.headers()
            body = {"message": "1+1", "session_id": self.session}
            created = self.client.post("/api/agent/jobs", json=body, headers=headers)
            self.assertEqual(202, created.status_code, created.get_json())
            job_id = created.get_json()["job_id"]
            terminal = self.terminal(job_id)
            self.assertEqual("succeeded", terminal["status"], terminal)
            contract = terminal["result"]["faithful"]
            self.assertEqual("faithful-task-v1", contract["version"])
            self.assertEqual(1, contract["input_version"])
            self.assertEqual(1, contract["specification_version"])
            self.assertEqual("completed", contract["phase"])
            self.assertEqual([], contract["allowed_actions"])
            self.assertTrue(contract["capability_snapshot"]["features"]["auto_problem_spec"])
            self.assertEqual("experimental", contract["capability_snapshot"]["maturity"])
            repeated = self.client.post("/api/agent/jobs", json=body, headers=headers)
            self.assertEqual(job_id, repeated.get_json()["job_id"])
        report = self.report(job_id)
        self.assertIn("2", report["answer"])
        self.assertEqual(4, len(self.outbound))
        self.assertEqual(contract, self.client.get(f"/api/agent/jobs/{job_id}").get_json()["result"]["faithful"])
        self.assertEqual("problem_intake", self.outbound[0]["role"])
        self.assertEqual("1+1", self.outbound[1]["problem_spec"]["original_problem"])
        self.assertEqual(4, terminal["result"]["budget"]["logical_calls"])
        self.assertEqual(report["answer"], self.report(job_id)["answer"])
        self.assertEqual(4, len(self.outbound))
