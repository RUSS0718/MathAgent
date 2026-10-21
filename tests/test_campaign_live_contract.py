"""Opt-in pipeline campaigns use a deterministic HTTP provider, never the network."""

from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import InternModelAdapter
from showcase.flask_app import create_app
from showcase.live_pipeline import LiveAgentPipeline
from showcase.tools import ToolRegistry
from tests.test_campaigns import CampaignFixture, campaign_input


class Response:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {
            "id": "fake-http",
            "model": "intern-s2-fixture",
            "choices": [{"finish_reason": "stop", "message": {"content": "2"}}],
        }


class LiveCampaignContractTest(CampaignFixture):
    def setUp(self):
        super().setUp()
        self.app.extensions["showcase_workspace_service"].close()
        self.app.extensions["showcase_run_service"].close()
        self.app.extensions["loopback_store"].close()
        model = InternModelAdapter(InternChatClient(retry=1), max_tokens=256, thinking_mode=True)
        registry = ToolRegistry()
        registry.register_polynomial_check()
        pipeline = LiveAgentPipeline(model, registry, execution_mode="fake")
        self.app = create_app(
            {
                "TESTING": True,
                "SHOWCASE_MODE": "live",
                "SHOWCASE_DATA_DIR": str(self.root / "artifacts" / "live-workspace"),
                "SHOWCASE_JOB_DELAY_SECONDS": 0,
                "SHOWCASE_LIVE_PIPELINE": pipeline,
                "SHOWCASE_CAMPAIGNS_LIVE_ENABLED": True,
            }
        )
        self.client = self.app.test_client()
        self.csrf = self.client.get("/api/check_auth").get_json()["csrf_token"]

    def test_capabilities_identify_fake_provider_in_live_orchestration(self):
        execution = self.client.get('/api/capabilities').get_json()['execution']
        self.assertEqual('fake', execution['mode'])
        self.assertEqual('fake', execution['provider'])

    def test_restart_keeps_fake_identity_for_unstarted_job_report_and_evidence(self):
        self.app.extensions["showcase_workspace_service"].worker_enabled = False
        payload = campaign_input()
        payload["allow_network"] = True
        created = self.submit(payload).get_json()
        job_id = created["pairs"][0]["arms"]["candidate"]["job_id"]
        second = create_app({**self.app.config, "SHOWCASE_WORKER_ENABLED": False})
        try:
            browser = second.test_client()
            browser.get("/api/check_auth")
            job = browser.get(f"/api/agent/jobs/{job_id}").get_json()
            self.assertEqual("needs_review", job["error"])
            self.assertEqual("fake", browser.get(f"/api/agent/jobs/{job_id}/report").get_json()["mode"])
            self.assertEqual("fake", browser.get(f"/api/runs/{job_id}/evidence").get_json()["mode"])
        finally:
            second.extensions["showcase_workspace_service"].close()
            second.extensions["showcase_run_service"].close()
            second.extensions["loopback_store"].close()

    def test_deadline_keeps_fake_identity_in_report_and_evidence(self):
        payload = campaign_input()
        payload["allow_network"] = True
        payload["budget"]["max_runtime_seconds"] = 0
        report = self.finished(self.submit(payload).get_json()["campaign_id"])
        for arm in report["pairs"][0]["arms"].values():
            self.assertEqual("run_deadline_exhausted", arm["error"])
            self.assertEqual("fake", self.client.get(arm["report_url"]).get_json()["mode"])
            self.assertEqual("fake", self.client.get(arm["evidence_url"]).get_json()["mode"])

    def test_generic_fake_pipeline_failure_keeps_persisted_mode(self):
        import time
        import uuid

        class FailingPipeline:
            execution_mode = "fake"

            def run(self, *args, **kwargs):
                raise RuntimeError("private failure must not reach report")

        self.app.extensions["showcase_workspace_service"].pipeline = FailingPipeline()
        headers = {"X-CSRF-Token": self.csrf}
        session_id = self.client.post("/api/new_chat", headers=headers).get_json()["new_session_id"]
        created = self.client.post("/api/agent/jobs", json={"message": "Compute 1+1.", "session_id": session_id}, headers={**headers, "Idempotency-Key": str(uuid.uuid4())}).get_json()
        job_id = created["job_id"]
        for _ in range(200):
            job = self.client.get(f"/api/agent/jobs/{job_id}").get_json()
            if job["status"] == "failed":
                break
            time.sleep(0.01)
        self.assertEqual("job_execution_failed", job["error"])
        self.assertEqual("fake", self.client.get(f"/api/agent/jobs/{job_id}/report").get_json()["mode"])
        self.assertEqual("fake", self.client.get(f"/api/runs/{job_id}/evidence").get_json()["mode"])

    def test_terminal_campaign_metrics_and_archive_remain_frozen_in_future(self):
        import time
        payload = campaign_input()
        payload["allow_network"] = True
        payload["budget"].update(max_model_calls=6, max_http_attempts=6, max_tokens=20_000)
        with patch("llm_client.requests.post", return_value=Response()):
            before = self.finished(self.submit(payload).get_json()["campaign_id"])
        with patch("showcase.run_budget.time.time", return_value=time.time() + 3600):
            after = self.detail(before["campaign_id"])
        self.assertEqual(before, after)
        for arm in after["pairs"][0]["arms"].values():
            self.assertIsNotNone(arm["budget"]["ended_at"])

    def test_offline_cannot_dispatch_through_a_live_workspace(self):
        with patch("llm_client.requests.post", side_effect=AssertionError("network forbidden")):
            response = self.submit()
        self.assertEqual(409, response.status_code)
        self.assertEqual("campaign_network_disabled", response.get_json()["error"])

    def test_closing_pipeline_workspace_keeps_borrowed_run_connection_available(self):
        payload = campaign_input()
        payload["allow_network"] = True
        payload["budget"].update(max_model_calls=6, max_http_attempts=6, max_tokens=20_000)
        with patch("llm_client.requests.post", return_value=Response()):
            report = self.finished(self.submit(payload).get_json()["campaign_id"])
        job_id = report["pairs"][0]["arms"]["baseline"]["job_id"]
        self.app.extensions["showcase_workspace_service"].close()
        self.assertEqual(200, self.client.get(f"/api/runs/{job_id}").status_code)

    def test_opt_in_fake_http_retains_unknown_usage_and_actual_common_limits(self):
        payload = campaign_input()
        payload["allow_network"] = True
        payload["budget"].update(max_model_calls=6, max_http_attempts=6, max_tokens=20_000)
        with patch("llm_client.requests.post", return_value=Response()):
            response = self.submit(payload)
            self.assertEqual(202, response.status_code)
            report = self.finished(response.get_json()["campaign_id"])
        self.assertEqual("fake", report["mode"])
        for arm in report["pairs"][0]["arms"].values():
            self.assertEqual("succeeded", arm["status"], arm)
            public_report = self.client.get(arm['report_url']).get_json()
            self.assertIn('离线 fake', public_report['report']['public_summary'])
            self.assertEqual(payload["budget"], arm["budget"]["limits"])
            self.assertGreater(arm["usage"]["unknown_attempts"], 0)
            self.assertIsNone(arm["usage"]["provider_known"]["total_tokens"])
            self.assertIsNone(arm["cost"])
            self.assertEqual(["intern-s2-fixture"], arm["returned_models"])
            self.assertTrue(all(a["run_id"] == arm["job_id"] for a in arm["request_attempts"]))
            self.assertEqual(arm['usage']['http_attempts'], len(arm['request_attempts']))
            self.assertEqual(len(arm['request_attempts']), len({a['attempt_id'] for a in arm['request_attempts']}))
            self.assertTrue(all(a['dispatch_status'] == 'transport_observed' for a in arm['request_attempts']))

    def test_http_attempt_cap_is_applied_to_each_arm_and_failure_retained(self):
        payload = campaign_input()
        payload["allow_network"] = True
        payload["budget"].update(max_model_calls=6, max_http_attempts=1, max_tokens=20_000)
        with patch("llm_client.requests.post", return_value=Response()):
            response = self.submit(payload)
            self.assertEqual(202, response.status_code)
            report = self.finished(response.get_json()["campaign_id"])
        self.assertEqual(1, report["summary"]["total_pairs"])
        for arm in report["pairs"][0]["arms"].values():
            self.assertEqual("failed", arm["status"])
            self.assertEqual(1, arm["usage"]["http_attempts"])
