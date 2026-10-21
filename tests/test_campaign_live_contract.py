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
            self.assertEqual(payload["budget"], arm["budget"]["limits"])
            self.assertGreater(arm["usage"]["unknown_attempts"], 0)
            self.assertIsNone(arm["usage"]["provider_known"]["total_tokens"])
            self.assertIsNone(arm["cost"])
            self.assertEqual(["intern-s2-fixture"], arm["returned_models"])
            self.assertTrue(all(a["run_id"] == arm["job_id"] for a in arm["request_attempts"]))

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
