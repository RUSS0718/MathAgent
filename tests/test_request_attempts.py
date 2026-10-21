from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import InternModelAdapter
from showcase.flask_app import create_app
from showcase.live_pipeline import LiveAgentPipeline
from showcase.tools import ToolRegistry


class ProviderResponse:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {
            "id": "provider-123",
            "model": "intern-s2-returned",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": "2", "reasoning_content": "NEVER_EXPORT_THINKING"},
                }
            ],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
        }


class RequestAttemptContractTest(unittest.TestCase):
    def test_workspace_report_persists_provider_attempts(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, {"INTERN_API_KEY": "fake-key"}),
            patch("llm_client.requests.post", return_value=ProviderResponse()),
        ):
            model = InternModelAdapter(InternChatClient(retry=1), max_tokens=256)
            app = create_app(
                {
                    "TESTING": True,
                    "SHOWCASE_MODE": "live",
                    "SHOWCASE_DATA_DIR": directory,
                    "SHOWCASE_LIVE_PIPELINE": LiveAgentPipeline(model, ToolRegistry()),
                }
            )
            client = app.test_client()
            csrf = client.get("/api/check_auth").get_json()["csrf_token"]
            headers = {"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())}
            session = client.post("/api/new_chat", headers=headers).get_json()["new_session_id"]
            job_id = client.post(
                "/api/agent/jobs", json={"message": "1+1", "session_id": session}, headers=headers
            ).get_json()["job_id"]
            for _ in range(200):
                job = client.get(f"/api/agent/jobs/{job_id}").get_json()
                if job["status"] in {"succeeded", "failed"}:
                    break
                time.sleep(0.01)
            report = client.get(f"/api/agent/jobs/{job_id}/report").get_json()["report"]
            self.assertEqual("succeeded", job["status"])
            self.assertEqual(3, len(report["request_attempts"]))
            attempt = report["request_attempts"][0]
            self.assertEqual(job_id, attempt["run_id"])
            self.assertEqual("planner", attempt["role"])
            self.assertEqual("intern-s2-returned", attempt["returned_model"])
            self.assertEqual(10, attempt["usage"]["total_tokens"])
            self.assertEqual("intern-s2", attempt["requested_model"])
            self.assertEqual("provider-123", attempt["provider_request_id"])
            self.assertEqual("stop", attempt["finish_reason"])
            self.assertIsNone(attempt["cost"])
            evidence = client.get(f"/api/runs/{job_id}/evidence").get_json()
            self.assertEqual(report["request_attempts"], evidence["request_attempts"])
            self.assertNotIn("NEVER_EXPORT", json.dumps(report))
            for key in ("showcase_workspace_service", "showcase_run_service", "loopback_store"):
                app.extensions[key].close()

    def test_adapter_usage_is_nullable_and_does_not_invent_total(self):
        for supplied, expected in [
            (
                {"prompt_tokens": 7},
                {"prompt_tokens": 7, "completion_tokens": None, "total_tokens": None},
            ),
            (None, {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}),
            (
                {"prompt_tokens": True, "completion_tokens": -1, "total_tokens": "8"},
                {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None},
            ),
        ]:
            with (
                self.subTest(supplied=supplied),
                patch.dict(os.environ, {"INTERN_API_KEY": "fake-key"}),
                patch("llm_client.requests.post") as post,
            ):
                response = ProviderResponse().json()
                response["usage"] = supplied
                post.return_value.status_code = 200
                post.return_value.json.return_value = response
                answer = InternModelAdapter(InternChatClient(retry=1)).complete(
                    [{"role": "user", "content": "1+1"}],
                    metadata={"run_id": "run-one", "role": "solver"},
                )
                attempt = answer.request_attempts[0]
                for key, value in expected.items():
                    self.assertEqual(value, answer.usage[key])
                    self.assertEqual(value, attempt["usage"][key])
                self.assertEqual("unknown", attempt["metering_status"])

    def test_failed_retry_is_preserved_in_request_scoped_result(self):
        import requests

        with (
            patch.dict(os.environ, {"INTERN_API_KEY": "fake-key"}),
            patch(
                "llm_client.requests.post",
                side_effect=[requests.Timeout("NEVER_EXPORT"), ProviderResponse()],
            ),
            patch("llm_client.time.sleep"),
        ):
            answer = InternModelAdapter(InternChatClient(retry=2)).complete(
                [{"role": "user", "content": "1+1"}], metadata={"run_id": "run-retry"}
            )
        self.assertEqual(["error", "success"], [item["status"] for item in answer.request_attempts])
        self.assertEqual("timeout", answer.request_attempts[0]["stop_category"])
        self.assertEqual(
            answer.request_attempts[0]["logical_call_id"],
            answer.request_attempts[1]["logical_call_id"],
        )
        self.assertNotEqual(
            answer.request_attempts[0]["attempt_id"], answer.request_attempts[1]["attempt_id"]
        )
        self.assertIsNone(answer.request_attempts[0]["usage"]["total_tokens"])
        self.assertNotIn("NEVER_EXPORT", json.dumps(answer.request_attempts))

    def test_invalid_response_and_http_error_preserve_failed_attempts(self):
        import requests

        from showcase.adapters import AdapterError

        for kind in ("invalid", "http", "timeout"):
            with (
                self.subTest(kind=kind),
                patch.dict(os.environ, {"INTERN_API_KEY": "fake-key"}),
                patch("llm_client.requests.post") as post,
            ):
                response = post.return_value
                response.status_code = 503 if kind == "http" else 200
                if kind == "http":
                    response.raise_for_status.side_effect = requests.HTTPError(
                        "NEVER_EXPORT", response=response
                    )
                elif kind == "timeout":
                    post.side_effect = requests.Timeout("NEVER_EXPORT")
                else:
                    response.json.return_value = {"choices": []}
                with self.assertRaises(AdapterError) as raised:
                    InternModelAdapter(InternChatClient(retry=1)).complete(
                        [{"role": "user", "content": "1+1"}]
                    )
                self.assertEqual(
                    {"invalid": "invalid_response", "http": "http_status", "timeout": "timeout"}[
                        kind
                    ],
                    raised.exception.category,
                )
                self.assertEqual(1, len(raised.exception.request_attempts))
                self.assertEqual("error", raised.exception.request_attempts[0]["status"])

    def test_g1_pins_request_and_blocks_without_retry(self):
        import requests

        from showcase.s1_probe import S1ProbePipeline

        for failure in (False, True):
            with (
                self.subTest(failure=failure),
                patch.dict(
                    os.environ,
                    {
                        "INTERN_API_KEY": "fake-key",
                        "INTERN_MODEL": "intern-latest",
                        "INTERN_RETRY_COUNT": "9",
                        "INTERN_THINKING_MODE": "false",
                    },
                ),
                patch("llm_client.requests.post") as post,
            ):
                if failure:
                    post.side_effect = requests.Timeout("NEVER_EXPORT")
                else:
                    post.return_value = ProviderResponse()
                result = S1ProbePipeline().run("g1-run", "unused")
                self.assertEqual(1, post.call_count)
                payload = json.loads(post.call_args.kwargs["data"])
                self.assertEqual("intern-s2", payload["model"])
                self.assertEqual(256, payload["max_tokens"])
                self.assertIs(True, payload["thinking_mode"])
                self.assertEqual("FAILED" if failure else "COMPLETED", result["status"])
                self.assertEqual(1, len(result["request_attempts"]))
                self.assertEqual("g1-run", result["request_attempts"][0]["run_id"])

    def test_concurrent_runs_keep_attempts_local(self):
        from concurrent.futures import ThreadPoolExecutor

        with (
            patch.dict(os.environ, {"INTERN_API_KEY": "fake-key"}),
            patch("llm_client.requests.post", return_value=ProviderResponse()),
        ):
            pipeline = LiveAgentPipeline(
                InternModelAdapter(InternChatClient(retry=1)), ToolRegistry()
            )
            with ThreadPoolExecutor(max_workers=2) as pool:
                states = list(pool.map(lambda run: pipeline.run(run, "1+1"), ["run-a", "run-b"]))
        ids = []
        for state in states:
            self.assertEqual(3, len(state["request_attempts"]))
            self.assertEqual(
                {state["run_id"]}, {item["run_id"] for item in state["request_attempts"]}
            )
            ids.extend(item["attempt_id"] for item in state["request_attempts"])
        self.assertEqual(6, len(set(ids)))

    def test_missing_response_identity_still_has_local_attempt_id(self):
        with (
            patch.dict(os.environ, {"INTERN_API_KEY": "fake-key"}),
            patch("llm_client.requests.post") as post,
        ):
            post.return_value.status_code = 200
            post.return_value.json.return_value = {"choices": [{"message": {"content": "2"}}]}
            answer = InternModelAdapter(InternChatClient(retry=1)).complete(
                [{"role": "user", "content": "1+1"}]
            )
        attempt = answer.request_attempts[0]
        self.assertTrue(attempt["attempt_id"])
        self.assertIsNone(attempt["provider_request_id"])
        self.assertIsNone(attempt["finish_reason"])
        self.assertIsNone(attempt["returned_model"])


if __name__ == "__main__":
    unittest.main()
